import os
import zipfile
import ast
import time
import base64

from rest_framework import viewsets, permissions
from django.conf import settings
from django.contrib.auth.models import User
from conversation.models import Conversation, Messages
from .executor.utils import invoke_model
from .executor.outputparser import FilepathResponse
from .serializers import ProjectSerializer, FileSerializer, DocumentDetailFetchSerializer
from django.contrib.auth import authenticate
from rest_framework.permissions import IsAuthenticated
from rest_framework.authtoken.models import Token
from rest_framework.decorators import permission_classes
from rest_framework.decorators import api_view, action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import Project, File, ImageUpload
from langchain.memory import ConversationSummaryBufferMemory
from code_reader.utils import llm, call_openai_llm_without_memory, summary_maker_chain, encode_image, \
    call_openai_llm_with_image
from code_reader.executor.main import call_executor
from langchain.docstore.document import Document
from code_reader.utils import call_openai_llm_without_memory


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer

    def perform_create(self, serializer):
        if serializer.is_valid():
            project = serializer.save()
            zip_file = project.zip_file

            if zip_file:
                new_repo_path = os.path.join(settings.MEDIA_ROOT, project.name)
                os.makedirs(new_repo_path, exist_ok=True)

                with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                    zip_ref.extractall(new_repo_path)

                files = os.listdir(new_repo_path)
                if len(files) == 1 and os.path.isdir(os.path.join(settings.MEDIA_ROOT, project.name, files[0])):
                    new_repo_path = os.path.join(settings.MEDIA_ROOT, project.name, files[0])

                project.repo_path = new_repo_path
                project.save()


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


@api_view(['POST'])
def login_view(request):
    username = request.data.get('username')
    password = request.data.get('password')
    user = authenticate(username=username, password=password)
    if user is not None:
        token, created = Token.objects.get_or_create(user=user)
        return Response({'token': token.key})
    else:
        return Response({'error': 'Invalid credentials'}, status=400)


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


class QueryView(APIView):
    def post(self, request, project_id):
        # Retrieve the project instance
        project = get_object_or_404(Project, id=project_id)

        # Extract the user's query from the request
        user_query = request.data['query']
        files = list(File.objects.filter(project=project).values('path', 'summary'))
        if len(str(files)) > 50000 and not project.files_summary:
            documents = [Document(page_content=file['summary'], metadata={"path": file['path']}) for file in files]
            result = summary_maker_chain.invoke(documents)
            files = result
            project.files_summary = files
            project.save()
            print("Summary Results of files: ", result)
        else:
            files = project.files_summary

        if user_query:
            # Initialize the OpenAI API with your API key

            # Prepare the prompt or input for the LLM
            prompt = f"""
                Project data: ##{project.name}##\n
                Project summary: ##{project.summary}##\n
                Files summary docs: ##{files}##\n\n
                Based on the above given data, Answer the following questions:
                User Query: ##{user_query}##\n\n
                Notes for you answer: 
                    1. if the question is about changing or adding something in the project's code,
                     make the answer so that you will be telling what user needs to do. \n
                    2. if the question is about some information of the code, answer it 
                     in structured way for human to understand and in detail\n\n
                Answer:
            """
            print(prompt)

            try:

                # Call the GPT-4o model
                print("going to call for answer from llm")
                answer = call_openai_llm_without_memory(prompt)
                print(f"answer: {answer}")
                # Extract the generated answer
                call_executor(project.repo_path, answer, project, settings.BASE_DIR)
                # Return the answer as a JSON response
                return Response({'answer': answer}, status=status.HTTP_200_OK)

            except Exception as e:
                # Handle exceptions and return an error response
                return Response({'error': str(e)}, status=500)

        else:
            # Handle the case where 'query' is not provided in the request
            return Response({'error': 'No query provided.'}, status=400)


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
        files = list(File.objects.filter(project=project).values('path', 'summary'))
        if len(str(files)) > 50000 and not project.files_summary:
            documents = [Document(page_content=file['summary'], metadata={"path": file['path']}) for file in files]
            result = summary_maker_chain.invoke(documents)
            files = result
            project.files_summary = files
            project.save()
            print("Summary Results of files: ", result)
        else:
            files = project.files_summary

        if user_query:
            prompt = f"""
                #         Project data: ##{project.name}##\n
                #         Project summary: ##{project.summary}##\n
                #         Files summary docs: ##{files}##\n
                #         Summary of the conversation : ##{str(summary_memory.load_memory_variables({}))}##\n\n
                #         Based on the above given data, Answer the following questions:
                #         User Query: ##{user_query}##\n\n
                #         Yours Instruction: 
                            1. give me file paths of all the files that you need the content for giving better information for user query
                
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
                     make the answer so that you will be telling what user needs to do. \n
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
        user_query, base64_image = self.process_user_inputs(request, project)

        # Prepare prompt
        prompt, summary_memory = self.prepare_prompt(project, user_query, conversation_obj)

        # Call LLM and handle execution
        try:
            answer = self.call_llm(prompt, base64_image)
            self.save_interaction(conversation_obj, summary_memory,user_query, answer)
            call_executor(project.repo_path, answer, project, settings.BASE_DIR, base64_image)
            return Response({'answer': answer}, status=200)
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
        base64_image = encode_image(user_file) if user_file else ""
        if user_file:
            ImageUpload.objects.create(project=project, image=user_file, extracted_content="")
        return user_query, base64_image

    def prepare_prompt(self, project, user_query, conversation_obj):
        # Prepare conversation history
        summary_memory = ConversationSummaryBufferMemory(llm=llm, max_token_limit=500)
        conv_summary = "No conversation yet\n"
        if 'history' in conversation_obj.conversation_summary:

            conv_summary = ast.literal_eval(conversation_obj.conversation_summary)['history']
            summary_memory.save_context({"input": "conversation till now"}, {"output": conv_summary})

        files = list(File.objects.filter(project=project).values('path', 'summary'))
        if len(str(files)) > 50000:
            documents = [Document(page_content=file['summary'], metadata={"path": file['path']}) for file in files]
            files = summary_maker_chain.invoke(documents)
            project.summary = files
            project.save()
        code_context = "no files present, yet to build the project"
        if user_query and files:
            prompt_for_fetching_file = f"""
                #         Project data: ##{project.name}##\n
                #         Project summary: ##{project.summary}##\n
                #         Files summary docs: ##{files}##\n
                #         Summary of the conversation : ##{str(conv_summary)}##\n\n
                #         Based on the above given data, Answer the following questions:
                #         User Query: ##{user_query}##\n\n
                #         Yours Instruction: 
                            1. give me file paths of all the files that you need the content so that you can
                            interpret user requests and provide actionable insights for a project's code.

                    """
            response = invoke_model(prompt_for_fetching_file, FilepathResponse)
            file_paths = response.model_dump()['files']
            print('file_paths retrieved: ')
            print(file_paths)
            code_context = File.objects.filter(path__in=file_paths).values('path', 'content', 'summary')
            if len(str(code_context)) > 50000:
                code_context = File.objects.filter(path__in=file_paths).values('path', 'content')

            print('code_context retrieved')
        else:
            print('no code_context before, yet to build the project')
        # print(code_context)

        # Prepare the prompt or input for the LLM
        prompt = f"""
            You are an AI assistant designed to interpret user requests and provide actionable insights for a project's code.
            Below is the project information, including its file structure, summary, and individual file details.
            ### Project Information:
            - **File Structure**: {project.tree_structure}
            - **Project Summary**: {project.summary}
            - **Related Files content and summary**: {code_context}
            - **Summary of the conversation**: {conv_summary}
            ### User Query:
            {user_query}
            ### Response:
        """

        return prompt, summary_memory

    def call_llm(self, prompt, base64_image):
        if base64_image:
            return call_openai_llm_with_image(prompt, base64_image)
        return call_openai_llm_without_memory(prompt)

    def save_interaction(self, conversation_obj, summary_memory, user_query, answer):
        Messages.objects.create(conversation=conversation_obj, user_message=user_query, ai_response=answer)
        summary_memory.save_context({"input": user_query}, {"output": answer})
        conversation_obj.conversation_summary = summary_memory.load_memory_variables({})
        conversation_obj.save()


class ProjectFilesView(APIView):
    def get(self, request, project_id):
        project = get_object_or_404(Project, id=project_id)
        files = File.objects.filter(project=project).values('path', 'content')
        return Response({
            "project_tree_structure": project.tree_structure,
            "files": list(files)
        },
        status=status.HTTP_200_OK)


class UserDetailView(APIView):
    @permission_classes([IsAuthenticated])
    def get(self, request):
        print()
        token_key = request.headers.get('Authorization').split(" ")[1]
        token = Token.objects.get(key=token_key)
        user = token.user
        user_details = {
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name
        }
        return Response(user_details, status=status.HTTP_200_OK)