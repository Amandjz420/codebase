# executor/utils.py

import os
import json
import platform
import re
import time
import threading
import tempfile
import subprocess
import shlex
from typing import Union, Type, List
from langchain.schema import HumanMessage
from langchain.output_parsers import PydanticOutputParser
from dotenv import load_dotenv
from pydantic import BaseModel

from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from django.conf import settings

# Function to check if tmux is installed

# def check_tmux_installed():
#     try:
#         subprocess.run(['tmux', '-V'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
#         return True
#     except FileNotFoundError:
#         raise RuntimeError("tmux is not installed. Please install it using 'sudo apt install tmux'.")
# # Invoke the check at the start of the script
# tmux_installed = check_tmux_installed()

# Set your OpenAI API key as an environment variable for security
OPENAI_API_KEY = settings.OPEN_AI_KEY
if not OPENAI_API_KEY:
    raise ValueError("Please set the OPENAI_API_KEY environment variable.")

# Initialize LLM
llm = ChatOpenAI(
    api_key=OPENAI_API_KEY,
    temperature=0.7,
    model_name='gpt-4o',
)
# llm = ChatGroq(
#     model="llama-3.3-70b-versatile",  # Specify the desired model
#     temperature=0.7,             # Adjust the temperature as needed
#     api_key=OPENAI_API_KEY,             # Set the maximum number of tokens
#     timeout=60,                  # Set a timeout for API requests
#     max_retries=3                # Define the number of retries for failed requests
# )

smarter_llm = ChatOpenAI(
    api_key=OPENAI_API_KEY,
    model_name='o3-mini',
    temperature=1
)

# smarter_llm = ChatGroq(
#     model="llama3-70b-8192",  # Specify the desired model
#     temperature=0.7,             # Adjust the temperature as needed
#     api_key=OPENAI_API_KEY,             # Set the maximum number of tokens
#     timeout=60,                  # Set a timeout for API requests
#     max_retries=3                # Define the number of retries for failed requests
# )

output_buffers = {}

def get_output_buffer(session_name: str) -> list:
    if session_name not in output_buffers:
        output_buffers[session_name] = []
    print("output_buffers")
    print(output_buffers)
    return output_buffers[session_name]

def generate_session_name(project_name):
    """
    Generates a 6-digit code based on the current time.

    Returns:
        int: A 6-digit code.
    """
    # Get the current time in seconds since the epoch
    current_time = int(time.time())

    # Modulo operation to ensure a 6-digit number
    code = current_time % 1000000
    SESSION_NAME = f"{project_name}-{code:06d}"
    # Ensure the code is zero-padded to 6 digits
    return SESSION_NAME

def invoke_model(prompt: str, response_model: Type[BaseModel], is_list: bool = False, intelligence: str ="medium", image="") -> Union[BaseModel, List[BaseModel]]:
    """
    Utility to invoke the language model and parse the response with the specified response model.
    """
    try:
        parser = PydanticOutputParser(pydantic_object=response_model)
        final_prompt = prompt + "\nOnly provide the output in JSON as specified. Do not add any text before or after.\n" + parser.get_format_instructions()
        if image:
            message_content = [
                {"type": "text", "text": final_prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image}"}}
            ]
            message = HumanMessage(content=message_content)
        else:
            message = HumanMessage(content=final_prompt)

        if intelligence == "medium" or image:
            response = llm.invoke([message])
        elif intelligence == "high":
            print("trying to invoke o1-preview")
            # o1-preview cant handle file data
            response = smarter_llm.invoke([HumanMessage(content=final_prompt)])

        response_content = response.content.strip()
        match = re.search(r"(?:\w+\n)?(.*)", response_content, flags=re.DOTALL)
        if match:
            response_content = match.group(1).strip()

        if is_list:
            response_json = json.loads(response_content)
            return [response_model.parse_obj(item) for item in response_json]
        else:
            return parser.parse(response_content)
    except Exception as e:
        raise RuntimeError(f"Error invoking model: {e}")

def start_tmux_session(session_name, directory):
    try:
        print("system platform: ", platform.system())
        if is_macos():
            print(" inside macos")
            # Existing AppleScript code for macOS
            commands = f"tmux new -s {shlex.quote(session_name)} -d; " \
                       f"tmux send-keys -t {shlex.quote(session_name)} 'cd {shlex.quote(directory)}' C-m; " \
                       f"tmux attach -t {shlex.quote(session_name)}"

            applescript_command = f'''
                tell application "Terminal"
                    do script "{commands}"
                    activate
                end tell
            '''
            subprocess.run(['osascript', '-e', applescript_command])
        else:
            print(" inside linux")
            print(f"ssh -t -i codeknot_dev_key.pem azureuser@172.206.95.24 'tmux attach-session -t {session_name}'")
            # Use shell command for Ubuntu
            subprocess.run(['tmux', 'new-session', '-d', '-s', session_name, f'cd {directory} && bash'])
    except subprocess.CalledProcessError as e:
        print(f"Failed to start tmux session '{session_name}' in directory '{directory}'. Error: {e}")

def send_command_to_tmux(session_name, command, delay=0.1):
    """
    Sends a command to the specified tmux session.
    """
    try:
        for char in command:
            subprocess.run(['tmux', 'send-keys', '-t', session_name, char])
            time.sleep(delay)  # Delay between each character
        subprocess.run(['tmux', 'send-keys', '-t', session_name, 'C-m'])
    except subprocess.CalledProcessError as e:
        print(f"Failed to send command to tmux session '{session_name}'. Command: {command}. Error: {e}")

def create_tmux_pane_logger(session_name, log_file):
    """
    Pipes the tmux pane output to a log file.
    """
    try:
        subprocess.run(['tmux', 'pipe-pane', '-o', '-t', session_name, f'cat >> {log_file}'])
    except subprocess.CalledProcessError as e:
        print(f"Failed to create tmux pane logger for session '{session_name}'. Log file: {log_file}. Error: {e}")

def monitor_log_file(log_file, output_buffer_arr):
    """
    Monitors the log file for output.
    """
    with open(log_file, 'r') as f:
        # Move to the end of the file
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if line:
                print(line, end='')  # Print the output to the console
                output_buffer_arr.append(line)
            else:
                time.sleep(0.1)

def start_tmux_session_with_logging(directory, project_name, session_name=""):
    if not session_name:
        # FIXME: remove the logic from here
        session_name = generate_session_name(project_name)
    # Start the tmux session
    try:
        start_tmux_session(session_name, directory)
    except ValueError as e:
        print(e)
        return

    time.sleep(2)
    print("Starting tmux session with", session_name)
    # Create a temporary log file to capture the pane output
    log_file = tempfile.NamedTemporaryFile(delete=False)
    log_file.close()

    # Start logging the tmux pane output
    create_tmux_pane_logger(session_name, log_file.name)
    output_buffer = get_output_buffer(session_name)

    # Start monitoring the log file in a separate thread
    monitor_thread = threading.Thread(target=monitor_log_file, args=(log_file.name, output_buffer), daemon=True)
    monitor_thread.start()

    return directory, session_name

def kill_tmux_session(session_name):
    """
    Kills a tmux session by its name.

    Args:
        session_name (str): The name of the tmux session to kill.

    Returns:
        bool: True if the session was killed successfully, False otherwise.
    """
    try:
        # Check if the session exists
        result = subprocess.run(["tmux", "has-session", "-t", session_name], stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            print(f"Session '{session_name}' does not exist or is already closed.")
            return False

        # Kill the session without user prompt
        subprocess.run(["tmux", "kill-session", "-t", session_name], check=True)
        print(f"Session '{session_name}' has been successfully killed.")
        return True

    except subprocess.CalledProcessError as e:
        print(f"Error killing session '{session_name}'. Command: kill-session. Error: {e}")
        return False

# Functions to identify the operating system
def is_macos():
    return platform.system() == 'Darwin'

def is_ubuntu():
    return platform.system() == 'Linux'