import json
import os
import zipfile
import ast
import time
import base64
from django.core.validators import validate_email
from rest_framework import viewsets, permissions
from django.conf import settings
from django.contrib.auth.models import User
from conversation.models import Conversation, Messages
from .executor.agent_functions import create_plan
from .executor.utils import invoke_model
from .executor.outputparser import FilepathResponse, SupervisorResponse
from .serializers import ProjectSerializer, FileSerializer, DocumentDetailFetchSerializer, StepSerializer
from django.contrib.auth import authenticate
from rest_framework.permissions import IsAuthenticated
from rest_framework.authtoken.models import Token
from rest_framework.decorators import permission_classes
from rest_framework.decorators import api_view, action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import Project, File, ImageUpload, ChangeRequested, Plan, Step
from .tasks import start_code_reading
from langchain.memory import ConversationSummaryBufferMemory
from code_reader.utils import llm, call_openai_llm_without_memory, summary_maker_chain, encode_image, \
    call_openai_llm_with_image, build_tree
from code_reader.executor.main import call_executor, call_executor_with_plan
from langchain.docstore.document import Document
from code_reader.utils import call_openai_llm_without_memory


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer

    def perform_create(self, serializer):
        if serializer.is_valid():
            project = serializer.save()
            zip_file = project.zip_file
            if len(project.repo_path) < 5:
                new_repo_path = os.path.join(settings.MEDIA_ROOT, project.name)
                os.makedirs(new_repo_path, exist_ok=True)
                print("extracting the zip archive")
                project.repo_path = new_repo_path
                project.save()

            if zip_file:
                new_repo_path = os.path.join(settings.MEDIA_ROOT, project.name)
                os.makedirs(new_repo_path, exist_ok=True)
                print("extracting the zip archive")

                with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                    zip_ref.extractall(new_repo_path)

                files = os.listdir(new_repo_path)
                if len(files) == 1 and os.path.isdir(os.path.join(settings.MEDIA_ROOT, project.name, files[0])):
                    new_repo_path = os.path.join(settings.MEDIA_ROOT, project.name, files[0])
                if len(files) == 2 and os.path.isdir(os.path.join(new_repo_path, '__MACOSX')):
                    new_repo_path = os.path.join(new_repo_path, files[0] if files[0] != '__MACOSX' else files[1])

                project.repo_path = new_repo_path
                project.save()
                start_code_reading.delay(project.id)

            return {"message": "Project created successfully", "id": project.id, "name": project.name}


class ProjectDetailViewSet(APIView):
    def get(self, request, pk=None):
        try:
            project = Project.objects.get(pk=pk)
            return Response(
                {
                    'tree_structure': project.tree_structure,
                    "repo_path": project.repo_path,
                    'summary': project.summary
                }
                , status=status.HTTP_200_OK
            )
        except Project.DoesNotExist:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)


class ProjectListViewSet(APIView):
    def get(self, request):
        try:
            project = Project.objects.all()
            return Response(
                [{"name": p.name, "id": p.id} for p in project]
                , status=status.HTTP_200_OK
            )
        except Project.DoesNotExist:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)


class FileViewSet(viewsets.ModelViewSet):
    queryset = File.objects.all()
    serializer_class = FileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return File.objects.filter(project__user=self.request.user)

class FileDetailViewSet(APIView):
    queryset = File.objects.all()
    serializer_class = FileSerializer
    def get(self, request, file_id):
        file = get_object_or_404(File, id=file_id)
        file_data = FileSerializer(file).data
        return Response(file_data, status=status.HTTP_200_OK)


@api_view(['POST'])
def login_view(request):
    username = request.data.get('username')
    password = request.data.get('password')
    first_name = request.data.get('first_name')
    last_name = request.data.get('last_name')

    if not username or not password:
        return Response({'error': 'Username and password are required.'}, status=status.HTTP_400_BAD_REQUEST)

    # Create user if first_name and last_name are provided
    if first_name and last_name:
        user, created = User.objects.get_or_create(username=username, defaults={
            'first_name': first_name,
            'last_name': last_name,
        })
        if created:
            user.set_password(password)  # Hash the password
            user.save()

    # Authenticate the user
    user = authenticate(username=username, password=password)
    if user is not None:
        token, _ = Token.objects.get_or_create(user=user)
        return Response({'token': token.key})
    else:
        return Response({'error': 'Invalid credentials'}, status=status.HTTP_400_BAD_REQUEST)


class DocumentDetailFetch(APIView):
    def post(self, request):
        serializer = DocumentDetailFetchSerializer(data=request.data)
        if serializer.is_valid():
            project_id = serializer.validated_data['project_id']
            fetch_field = serializer.validated_data['fetch_field']

            # Retrieve the project
            project = get_object_or_404(Project, id=project_id)

            # Fetch associated files
            files = File.objects.filter(project=project).values('path', *fetch_field)

            # Prepare the response data
            response_data = list(files)

            return Response(response_data, status=status.HTTP_200_OK)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class QnAView(APIView):

    def post(self, request, project_id, conversation_id):
        summary_memory = ConversationSummaryBufferMemory(llm=llm, max_token_limit=500)
        # Retrieve the project instance
        conv_summary = "nothing till now"
        conversation_obj, created = Conversation.objects.get_or_create(
            conversation_id=conversation_id,
            # FIXME: change the user based on user after authentication
            defaults={
                'user': User.objects.get(username='aman'),
                'conversation_summary': 'null'
            }
        )
        # print(conversation_obj)
        if 'history' in conversation_obj.conversation_summary:
            conversation_summary = ast.literal_eval(conversation_obj.conversation_summary)
            if 'history' in conversation_summary:
                conv_summary = conversation_summary['history']

        summary_memory.save_context({"input": "conversation till now"}, {"output": conv_summary})
        project = get_object_or_404(Project, id=project_id)
        print("here i was")

        # Extract the user's query from the request
        user_query = request.data['query']
        print(user_query)
        files = list(File.objects.filter(project=project, is_file_type=True).values('path', 'summary'))
        if len(str(files)) > 50000 and not project.files_summary:
            documents = [Document(page_content=file['summary'], metadata={"path": file['path']}) for file in files]
            result = summary_maker_chain.invoke(documents)
            files = result
            project.files_summary = files
            project.save()
            print("Summary Results of files: ", result)
        elif project.files_summary:
            files = project.files_summary
        code_context = "no files present, yet to build the project"
        if user_query and files:
            prompt = f"""
                #   Project data: ##{project.name}##\n
                #   Project summary: ##{project.summary}##\n
                #   Files summary docs: ##{files}##\n
                #   Summary of the conversation : ##{str(summary_memory.load_memory_variables({}))}##\n\n
                #  Based on the above given data, Answer the following questions:
                #  User Query: ##{user_query}##\n\n
                #  Yours Instruction: 
                     1. give me file paths of all the files that you need the content for giving better
                      information for user query
                    """
            response = invoke_model(prompt, FilepathResponse)
            file_paths = response.model_dump()['files']
            print('file_paths')
            print(file_paths)
            code_context = File.objects.filter(path__in=file_paths).values('path', 'content', 'summary')
            if len(str(code_context)) > 50000:
                code_context = File.objects.filter(path__in=file_paths).values('path', 'content')
            # parser = PydanticOutputParser(pydantic_object=response_model)
        if code_context:
            print('code_context')
            print(code_context)

            # Prepare the prompt or input for the LLM
            prompt = f"""
                Project data: ##{project.name}##\n
                Project summary: ##{project.summary}##\n
                Files summary and the content: ##{code_context}##\n
                Summary of the conversation : ##{str(summary_memory.load_memory_variables({}))}##\n\n
                Based on the above given data, Answer the following questions:
                User Query: ##{user_query}##\n\n
                Notes for you answer:
                    1. if the question is about changing or adding something in the project's code,
                     make the answer so that you will be telling what user needs to do in what all files. \n
                    2. if the question is about some information of the code, answer it
                     in structured way for human to understand and in detail\n\n
                Answer:

            """
            #  parser = PydanticOutputParser(pydantic_object=response_model)
            #         final_prompt = prompt + "\nOnly provide the output in JSON as specified. Do not add any text before or after.\n" + parser.get_format_instructions()
            #

            try:
                # Call the GPT-4o model
                print("going to call for answer from llm")
                answer = call_openai_llm_without_memory(prompt)

                # Saving the data in databases
                Messages.objects.create(conversation=conversation_obj, user_message=user_query, ai_response=answer)
                summary_memory.save_context({"input": user_query}, {"output": answer})
                conversation_obj.conversation_summary = summary_memory.load_memory_variables({})
                conversation_obj.save()

                # Return the answer as a JSON response
                print(answer)
                return Response({'answer': answer}, status=status.HTTP_200_OK)

            except Exception as e:
                # Handle exceptions and return an error response
                return Response({'error': str(e)}, status=500)

        else:
            # Handle the case where 'query' is not provided in the request
            return Response({'error': 'No query provided.'}, status=400)


class ExecutorView(APIView):
    def post(self, request, project_id, conversation_id):
        # Helper function to retrieve project and conversation
        project, conversation_obj = self.retrieve_project_and_conversation(project_id, conversation_id)

        # Process user inputs
        user_query, base64_image, executor_run = self.process_user_inputs(request, project)

        # Prepare prompt
        prompt, summary_memory, related_file_used = self.prepare_prompt(project, user_query, conversation_obj)

        # Call LLM and handle execution
        try:
            response = invoke_model(prompt, SupervisorResponse, image=base64_image)
            answer = response.model_dump()
            self.save_interaction(conversation_obj, summary_memory, user_query, answer['aiReply'])

            # If execution is required
            # Determine if executor is needed based on user_query
            print("condition for executor to be needed")
            print(SupervisorResponse.determine_executor_need(user_query))
            print(answer['isExecutionRequired'])
            print(answer['aiReply'])

            if SupervisorResponse.determine_executor_need(user_query) or answer['isExecutionRequired']:
                print("Executor needed based on user query.")
                change_requested_obj = ChangeRequested.objects.create(
                    description=answer['aiReply'],
                    project=project,
                    user_initial_query=user_query,
                    document_list=str(related_file_used),
                )
                session_name = f"CR{change_requested_obj.id}_session_executor"
                firebase_chat_id = f"CR{change_requested_obj.id}_session_executor"
                print(f"change_requested_obj: {change_requested_obj.id}")
                if executor_run:
                    executor_prompt = f"""
                                    User Initial Request: \n```{user_query}``\n\n
                                    And Code Reader suggested: \n###{answer['aiReply']}###\n\n
                                """
                    call_executor(
                        directory=project.repo_path,
                        user_request=executor_prompt,
                        project_obj=project,
                        BASE_DIR=settings.BASE_DIR,
                        reference_file=base64_image,
                        session_name=session_name,
                        firebase_chat_id=firebase_chat_id
                    )
                return Response({'answer': answer['aiReply'], "change_request_id": change_requested_obj.id}, status=200)

            return Response({'answer': answer['aiReply']}, status=200)
        except Exception as e:
            return Response({'error': str(e)}, status=500)

    def retrieve_project_and_conversation(self, project_id, conversation_id):
        project = get_object_or_404(Project, id=project_id)
        conversation_obj, created = Conversation.objects.get_or_create(
            conversation_id=conversation_id,
            # FIXME: change the user based on user after authentication
            defaults={'user': User.objects.get(username='aman'), 'conversation_summary': 'null'}
        )
        return project, conversation_obj

    def process_user_inputs(self, request, project):
        user_query = request.data.get('query')
        user_file = request.data.get('file', "")
        executor_run = request.data.get('executor_run', False)
        base64_image = encode_image(user_file) if user_file else ""
        if user_file:
            ImageUpload.objects.create(project=project, image=user_file, extracted_content="")
        return user_query, base64_image, executor_run

    def prepare_prompt(self, project, user_query, conversation_obj):
        # Prepare conversation history
        summary_memory = ConversationSummaryBufferMemory(llm=llm, max_token_limit=500)
        conv_summary = "No conversation yet\n"
        if 'history' in conversation_obj.conversation_summary:
            conv_summary = ast.literal_eval(conversation_obj.conversation_summary)['history']
            summary_memory.save_context({"input": "conversation till now"}, {"output": conv_summary})

        files = list(File.objects.filter(project=project, is_file_type=True).values('path', 'summary'))
        if len(str(files)) > 50000 and not project.files_summary:
            documents = [Document(page_content=file['summary'], metadata={"path": file['path']}) for file in files]
            result = summary_maker_chain.invoke(documents)
            files = result
            project.files_summary = files
            project.save()
            print("Summary Results of files: ", result)
        elif project.files_summary:
            files = project.files_summary
        code_context = "no files present, yet to build the project"
        if user_query and files:
            prompt_for_fetching_file = f"""
                #         Project data: ##{project.name}##\n
                #         Project summary: ##{project.summary}##\n
                #         Files summary docs: ##{files}##\n
                #         Summary of the conversation : ##{str(conv_summary)}##\n\n
                #         Based on the above given data, Answer the following questions:
                #         User's Query: ##{user_query}##\n\n
                #         Yours Instruction: 
                            1. give me file paths of all the files that you need the content so that you can
                            interpret user requests and provide actionable insights for a project's code.

                    """
            response = invoke_model(prompt_for_fetching_file, FilepathResponse)
            file_paths = response.model_dump()['files']
            print('file_paths retrieved: ')
            print(file_paths)
            related_file_used = file_paths
            code_context = File.objects.filter(path__in=file_paths).values('path', 'content', 'summary')
            if len(str(code_context)) > 50000:
                code_context = File.objects.filter(path__in=file_paths).values('path', 'content')

            print('code_context retrieved')
        else:
            print('no code_context before, yet to build the project')
            related_file_used = []
        # print(code_context)

        # Prepare the prompt or input for the LLM
        prompt = f"""
            You are an AI assistant designed to interpret user requests and provide actionable insights for a project's code.
            Below is the project information, including its file structure, summary, conversation history, and individual file details.
    
            ### Project Information:
            - **Project Name**: {project.name}
            - **File Structure**: {project.tree_structure}
            - **Project Summary**: {project.summary}
            - **Files Summary and Content**: {code_context}
            - **Summary of the Conversation**: {str(summary_memory.load_memory_variables({}))}
    
            ### User Query:
            ``{user_query}``
    
            ### Notes for Your Response:
            1. If the question is about modifying or adding something in the project's code,
                provide a detailed step-by-step response specifying what needs to be done in which files.
            2. If the question seeks information or explanation about the code, answer in a structured 
                and detailed manner for easy understanding.
            ### Response:
        """

        return prompt, summary_memory, related_file_used

    # def call_llm(self, prompt, base64_image):
    #     if base64_image:
    #         return call_openai_llm_with_image(prompt, base64_image)
    #     return call_openai_llm_without_memory(prompt)

    def save_interaction(self, conversation_obj, summary_memory, user_query, answer):
        Messages.objects.create(conversation=conversation_obj, user_message=user_query, ai_response=answer)
        summary_memory.save_context({"input": user_query}, {"output": answer})
        conversation_obj.conversation_summary = summary_memory.load_memory_variables({})
        conversation_obj.save()


class ProjectFilesView(APIView):
    def get(self, request, project_id):
        project = get_object_or_404(Project, id=project_id)

        # Fetch root-level files and folders (those without a parent)
        root_nodes = File.objects.filter(project=project, parent=None)

        # Build the tree structure starting from the root nodes
        project_tree = {
            'name': project.name,
            'type': 'folder',
            'filetype': 'none',
            'id': None,  # Root doesn't correspond to a File instance
            'children': [build_tree(node) for node in root_nodes]
        }

        return Response({
            'project_tree_structure': project_tree,
        }, status=status.HTTP_200_OK)

class ProjectReadFilesView(APIView):
    def get(self, request, project_id):
        project = get_object_or_404(Project, id=project_id)
        start_code_reading.delay(project.id)
        return Response({
            'message': "started reading the project: {}".format(project.name),
        }, status=status.HTTP_200_OK)


class UserDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        token_key = request.headers.get('Authorization').split(" ")[1]
        token = Token.objects.get(key=token_key)
        user = token.user
        user_details = {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name
        }
        return Response(user_details, status=status.HTTP_200_OK)


class ChangeRequestedView(APIView):
    def get(self, request, change_request_id):
        change_requested_obj = ChangeRequested.objects.get(id=change_request_id)
        change_data = {
            'document_list': change_requested_obj.document_list,
            'description': change_requested_obj.description,
            'created_at': change_requested_obj.created_at
        }
        return Response({'changes': change_data}, status=200)


class ChangeRequestedFeedbackView(APIView):
    def post(self, request, change_request_id):
        change_request_feedback = request.data.get('change_request_feedback')
        if not change_request_feedback:
            return Response({"error", "feedback is missing"}, status=status.HTTP_400_BAD_REQUEST)
        change_requested_obj = ChangeRequested.objects.get(id=change_request_id)
        if not change_requested_obj:
            return Response({"error", f"no change request object present for the id: {change_request_id}"},
                            status=status.HTTP_400_BAD_REQUEST)
        # Prepare prompt for OpenAI LLM
        #FIXME: have to support for fetching the right files too and passing it to context
        document_list = change_requested_obj.document_list
        # Convert the string to a Python list
        files_content = []
        try:
            document_list_array = ast.literal_eval(document_list)
            if document_list_array:
                files_content = File.objects.filter(path__in=document_list_array).values('path', 'content')
            print(document_list_array)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")

        prompt = (
            f"Related file content: {files_content}\n\n"
            f"User's initial query: {change_requested_obj.user_initial_query}\n"
            f"Previous description: {change_requested_obj.description}\n"
            f"Feedback: {change_request_feedback}\n\n"
            f"Refine the description based on the feedback and provide a better version."
        )
        # Call OpenAI function
        refined_content = call_openai_llm_without_memory(prompt)

        # Save the refined user feedback and content back to the database
        change_requested_obj.feedback = change_request_feedback
        change_requested_obj.description = refined_content
        change_requested_obj.save()

        # Return the refined content as the response
        return Response(
            {
                "message": "Feedback saved and description refined successfully.",
                "refined_description": refined_content,
            },
            status=200
        )


class ChangeRequestedPlanView(APIView):
    def get(self, request, change_request_id):
        change_requested_obj = ChangeRequested.objects.get(id=change_request_id)
        if not change_requested_obj:
            return Response({"error", f"no change request object present for the id: {change_request_id}"},
                            status=status.HTTP_400_BAD_REQUEST)
        # Prepare prompt for OpenAI LLM
        user_query = change_requested_obj.description
        document_list = change_requested_obj.document_list
        # Convert the string to a Python list
        files_content = []
        try:
            document_list_array = ast.literal_eval(document_list)
            if document_list_array:
                files_content = File.objects.filter(path__in=document_list_array).values('path', 'content')
            print(document_list_array)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")

        project_summary = (f"the project sumamry: \n{change_requested_obj.project.summary}\n\n "
                           f"The related document contents are: \n{files_content} ")
        plans = create_plan(user_query, project_summary)
        # FIXME: have to add logic for session_name and firebase_id
        session_name = f"CR{change_requested_obj.id}_session_executor"
        firebase_chat_id = f"CR{change_requested_obj.id}_session_executor"
        plan_object, created = Plan.objects.get_or_create(change_request=change_requested_obj,
                                                          defaults={
                                                              "session_name": session_name,
                                                              "firebase_chat_id": firebase_chat_id
                                                          })
        if not created:
            Step.objects.filter(plan=plan_object).delete()
        for order, step in enumerate(plans):
            print("order",order)
            print("step",step)
            Step.objects.create(
                order=order,
                plan=plan_object,
                title=step['title'],
                detailed_description=step['detailed_description'],
                pseudo_code=step['pseudo_code'],
                code_snippet=step['code_snippet']
            )

        return Response(
            {
                "message": f"Plan created and with the session_name: {session_name} ",
                "plan_id": plan_object.id,
                "steps": plans,
                "session_name": session_name,
                "firebase_chat_id": firebase_chat_id
            },
            status=200
        )

class PlanFeedbackView(APIView):

    def post(self, request, plan_id):
        plan_obj = Plan.objects.get(id=plan_id)
        plan_feedback = request.data.get('plan_feedback')
        change_requested_obj = plan_obj.change_request
        steps = Step.objects.filter(plan=plan_obj)
        steps_data = StepSerializer(steps, many=True).data
        # Prepare prompt for OpenAI LLM

        # prompt = (
        #     f"User's initial query: {change_requested_obj.user_initial_query}\n"
        #     f"Previous steps: {change_requested_obj.description}\n"
        #     f"Feedback: {change_request_feedback}\n\n"
        #     f"Refine the description based on the feedback and provide a better version."
        # )
        #
        # FIXME:  have to add the logic



class PlanExecutorView(APIView):

    def get(self, request, plan_id):
        plan_object = Plan.objects.get(id=plan_id)
        change_requested_obj = plan_object.change_request
        project = change_requested_obj.project
        session_name = plan_object.session_name
        firebase_chat_id = plan_object.firebase_chat_id
        steps = Step.objects.filter(plan=plan_object).order_by('-order')
        plans = StepSerializer(steps, many=True).data

        #  Reference file ????
        result = call_executor_with_plan(
            directory=project.repo_path,
            user_request=change_requested_obj.user_initial_query,
            plan=plans,
            project_obj=project,
            BASE_DIR=settings.BASE_DIR,
            reference_file='',
            session_name=session_name,
            firebase_chat_id=firebase_chat_id
        )

        if result == "done":
            return Response({"message": "Execution request by the user is completed"}, status.HTTP_200_OK)
        else:
            return Response({"message": f"Execution got halted with the following message: {result}"}, status.HTTP_500_INTERNAL_SERVER_ERROR)
