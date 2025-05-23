# executor/tools.py

import os
import time
from langchain_core.tools import tool
from langchain_community.utilities import SerpAPIWrapper
from typing import Dict, Any
from code_reader.executor.utils import send_command_to_tmux, invoke_model, start_tmux_session_with_logging
from code_reader.executor.outputparser import CodeUpdateResponse
from code_reader.models import Project
from code_reader.utils import run_file_summarizer, get_filtered_tree
from django.conf import settings


@tool
def terminal_executor(command: str) -> Dict[str, Any]:
    """
    Execute a shell command and return its output, error message, and exit code.
    """
    try:
        from code_reader.executor.utils import get_output_buffer, get_session_name
        # Safely split the command into arguments
        output_buffer = get_output_buffer()
        session_name = get_session_name()

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
def code_editor(filepath: str, instructions: str) -> str:
    """
    Edit or write code to a specified file based on the instructions provided.
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

        prompt = (
            f"{code_status}\n```\n{existing_code}\n```\n\n"
            f"Instructions:\n{instructions}\n\n"
            "Please provide the updated code incorporating the instructions above. "
            "Ensure that the code is complete, syntactically correct, and follows best practices."
            "and try to change what you need to change, and nothing extra."
        )

        updated_code_response = invoke_model(prompt, CodeUpdateResponse)
        updated_code = updated_code_response.updated_code.strip()

        # Optional: Validate the updated code (e.g., syntax check)

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
def starting_new_tmux_session_for_running_service(project_id, command):
    """
    will start a new tmux with command to run a service and add the logs to terminal session.
    :param project_id: id of the project
    :param command: command to run the server:
    :return:
    """
    from code_reader.executor.utils import get_output_buffer
    output_buffer = get_output_buffer()
    project = Project.objects.get(id=int(str(project_id)))

    directory, ses_name = start_tmux_session_with_logging(project.repo_path, project.name)
    send_command_to_tmux(ses_name, command)
    print(f"Waiting for command '{command}' to complete...")
    time.sleep(5)  # Adjust based on expected command duration
    # Collect output for analysis
    output = ''.join(output_buffer)
    output_buffer.clear()

    return f" at the directory: {directory}, new tmux session has been on with name: {ses_name} and is running the service using command: {command} resulting the output in terminal: {output}"

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
