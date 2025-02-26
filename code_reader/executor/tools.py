# executor/tools.py

import os
import time
from pathlib import Path

from langchain_core.tools import tool
from langchain_community.utilities import SerpAPIWrapper
from typing import Dict, Any
from code_reader.executor.utils import send_command_to_tmux, invoke_model, start_tmux_session_with_logging
from code_reader.executor.outputparser import CodeUpdateResponse
from code_reader.firebase import write_in_executor_firestore
from code_reader.models import Project, File
from code_reader.tasks import async_file_summarizer
from code_reader.utils import run_file_summarizer, get_filtered_tree
from django.conf import settings


@tool
def terminal_executor(command: str, session_name: str) -> Dict[str, Any]:
    """
    Execute a shell command on specific terminal session and return its output, error message, and exit code.
    """
    try:
        from code_reader.executor.utils import get_output_buffer
        # Safely split the command into arguments
        output_buffer = get_output_buffer(session_name)
        print("output_buffer")
        print(output_buffer)

        send_command_to_tmux(command=command, session_name=session_name)

        print(f"Waiting for command '{command}' to complete...")
        time.sleep(5)  # Adjust based on expected command duration
        # Collect output for analysis
        output = ''.join(output_buffer)
        output_buffer.clear()

        if command.startswith("cd "):
            if "No such file or directory" not in output:
                # Extract the path from the command
                new_dir = command.split(" ", 3)[1].strip()

                # Construct the full path relative to the current working directory
                full_path = os.path.abspath(os.path.join(os.getcwd(), new_dir))

                # Change the current working directory
                os.chdir(full_path)
                print(f"Changed working directory to: {os.getcwd()}")
            else:
                print(f"Failed to change directory: {output}")
        return {
            "message": output,
            "exit_code": 0
        }

    except Exception as e:
        return {
            "message": f"An error occurred: {str(e)}",
            "exit_code": -1
        }

@tool
def need_user_input(reason: str) -> str:
    """
    Gets a reason why user input is needed and asks for user input
    so that it can go back to planning according to user input.
    """
    print("Reason why user input is required:")
    print(reason)

    user_input = input("What would you like me to do? ")
    return user_input

@tool
def read_file_content(filepath: str) -> str:
    """
    read the content of the files.
    filepath - relative path of the file from current working directory
    instructions - instructions for the file at the path
    """
    try:
        # Resolve the absolute path
        absolute_filepath = os.path.join(os.getcwd(), filepath)
        absolute_filepath = os.path.abspath(absolute_filepath)

        # Ensure the directory exists
        directory = os.path.dirname(absolute_filepath)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)

        existing_code = ""
        if os.path.exists(absolute_filepath):
            with open(absolute_filepath, 'r') as file:
                existing_code = file.read()
            code_status = "The current code is:"
        else:
            code_status = "No existing code found at the specified path."

        return f"{code_status}\n```\n{existing_code}\n```\n\n"
    except Exception as e:
        return f"An error occurred while updating the file: {str(e)}"


@tool
def code_editor(filepath: str, instructions: str, current_project_id: int, create: bool, firebase_chat_id: str) -> str:
    """
    Edit or write code to a specified file based on the instructions provided.
    filepath - relative path of the file from current working directory
    instructions - instructions for the file at the path
    current_project_id - current project id
    create - true, if the file is not already there, and it will be created
    """
    try:
        # Resolve the absolute path
        absolute_filepath = os.path.join(os.getcwd(), filepath)
        absolute_filepath = os.path.abspath(absolute_filepath)
        # Ensure the directory exists
        directory = os.path.dirname(absolute_filepath)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)

        existing_code = ""
        if os.path.exists(absolute_filepath):
            with open(absolute_filepath, 'r') as file:
                existing_code = file.read()
            code_status = "The current code is:"
        else:
            with open(absolute_filepath, 'w') as file:
                file.write("")
            code_status = "No existing code found at the specified path."

        prompt = (
            f"{code_status}\n```\n{existing_code}\n```\n\n"
            f"Instructions:\n{instructions}\n\n"
            "Please provide the updated code incorporating the instructions above. "
            "Ensure that the code is complete, syntactically correct, and follows best practices."
            "and MAKE SURE to change ONLY what you need to change, "
            "and nothing extra in the current code (if code exists)"
        )

        updated_code_response = invoke_model(prompt, CodeUpdateResponse)
        updated_code = updated_code_response.updated_code.strip()
        file_changed = False
        with open(absolute_filepath, 'w') as file:
            file.write(updated_code)
        if create:
            async_file_summarizer.delay(current_project_id, absolute_filepath, updated_code=True)
            file_changed = True
        elif updated_code.strip() != existing_code.strip():
            file_obj = File.objects.filter(path=absolute_filepath, project_id=current_project_id).first()
            if file_obj:
                file_obj.updated_code = updated_code
                file_obj.save()
                file_changed = True
        if file_changed:
            write_in_executor_firestore(firebase_chat_id, data={
                'file_changed': True
            }, messages=False)
        with open(absolute_filepath, 'w') as file:
            file.write(updated_code)

        return f"File '{absolute_filepath}' was updated to: \n ``{updated_code}``\n"
    except Exception as e:
        return f"An error occurred while updating the file: {str(e)}"

@tool
def update_file_summary(project_id: str, absolute_file_path: str) -> str:
    """
    Take in the project ID and an absolute file path for the files that got changed dues to executor.
    It will return back the summary of the file and also update the summary of the file in database.
    """
    print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
    print(f"Updating summary for project {project_id} and path {absolute_file_path}")
    file_obj = run_file_summarizer(int(project_id), absolute_file_path)
    return file_obj.summary

@tool
def update_project_root_dir_and_tree_structure(project_id: str, absolute_path_prject: str) -> str:
    """
    Take in the project ID and an absolute file path for the newly created project and update it database.
    It will return back the path and tree structure
    :param
    project_id: project_id
    absolute_path_prject: the absolute path at which the project has been created.
    """
    project = Project.objects.get(id=int(str(project_id)))
    # initial_dir = os.getcwd()
    # os.chdir(absolute_path_prject)
    tree_structure_result = get_filtered_tree(absolute_path_prject)

    project.repo_path = absolute_path_prject
    project.tree_structure = tree_structure_result
    project.save()
    print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
    print(f"Updating repo_path and tree_structure for project {project_id}")
    # os.chdir(initial_dir)
    return f"New project path: {absolute_path_prject} \n tree structure: {tree_structure_result}\n\n"

@tool
def search_web_browser(query: str):
    """
    will search google using query given in parameters return back result
    :param query:
    :return:
    """
    serpapi = SerpAPIWrapper(serpapi_api_key=settings.SERPAPI_API_KEY)
    result = serpapi.run(query)
    return str(result)

@tool
def starting_new_tmux_session_for_running_service(project_id, command, session_name):
    """
    will start a new tmux with command to run a service and add the logs to terminal session.
    :param project_id: id of the project
    :param command: command to run the server:
    :project_run_session_name:  session name
    :return:
    """
    from code_reader.executor.utils import get_output_buffer
    output_buffer = get_output_buffer(f"{session_name}_run_project")
    project = Project.objects.get(id=int(str(project_id)))

    directory, ses_name = start_tmux_session_with_logging(
        project.repo_path, project.name, session_name=f"{session_name}_run_project"
    )
    send_command_to_tmux(ses_name, command)
    print(f"Waiting for command '{command}' to complete...")
    time.sleep(5)  # Adjust based on expected command duration
    # Collect output for analysis
    output = ''.join(output_buffer)
    output_buffer.clear()

    return (f" at the directory: {directory}, new tmux session has been on with name: {session_name}_run_project "
            f"and is running the service using command: {command} resulting the output in terminal: {output}")

@tool
def wait_for_some_time(seconds: str, reason_to_wait):
    """
    will be used to wait for another process to finish
    :param: seconds: time to wait for other thing to finish.
    :param: reason_to_wait reason to wait
    :return:string
    """
    time.sleep(int(seconds))
    return f"Waited for, {seconds} seconds, for reason {reason_to_wait}"
