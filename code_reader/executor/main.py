# executor/main.py

import os
import platform
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv
load_dotenv()

from code_reader.executor.agent_functions import planner, executor, feedback_analyzer, completion_check, AgentState
from code_reader.executor.utils import start_tmux_session_with_logging, kill_tmux_session


def main():
    # Set the working directory
    WORKING_DIRECTORY = '/Users/aman/PycharmProjects/pythonProject/'
    try:
        os.chdir(WORKING_DIRECTORY)
        print(f"Changed working directory to: {os.getcwd()}")
    except Exception as e:
        print(f"Failed to change directory: {e}")
        exit(1)

    if platform.system() != 'Darwin':
        print("This script uses AppleScript to open a new Terminal window and is only compatible with macOS.")
        return

    # Set the working directory
    directory = WORKING_DIRECTORY
    directory, session_name = start_tmux_session_with_logging("Aman", directory)

    # === Create and Compile Workflow ===
    workflow = StateGraph(AgentState)
    workflow.set_entry_point("planner")
    workflow.add_node("planner", planner)
    workflow.add_node("executor", executor)
    workflow.add_node("feedback_analyzer", feedback_analyzer)
    # workflow.add_node("completion_check", completion_check)
    workflow.add_edge("planner", "executor")
    workflow.add_edge("executor", "feedback_analyzer")
    # workflow.add_edge("feedback_analyzer", "completion_check")
    workflow.add_conditional_edges(
        "feedback_analyzer",
        completion_check,
        path_map={
            "executor": "executor",
            END: END,

        }
    )
    # Compile the graph
    graph = workflow.compile()
    code = """
    import os
import fnmatch
import subprocess
from dotenv import load_dotenv
from openai import OpenAI
from langchain.memory import ConversationSummaryBufferMemory
from langchain_openai import ChatOpenAI

load_dotenv()

# Initialize OpenAI and memory
client = OpenAI()
llm = ChatOpenAI(model='gpt-4o', temperature=0.5)
summary_memory = ConversationSummaryBufferMemory(llm=llm, max_token_limit=500)


def get_filtered_tree(directory):
    ""
    Runs the 'tree' command with exclusions and captures the output in a variable.

    Args:
    directory (str): The directory to run the tree command on. Defaults to the current directory.

    Returns:
    str: The output of the tree command.
    ""
    try:
        # Command to run `tree` with exclusions
        command = ["tree", "-I", ".next|node_modules|.git|venv|venv2|__pycache__", directory]
        # Execute the command and capture the output
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # Check for errors
        if result.returncode != 0:
            raise Exception(f"Error running tree command: {result.stderr}")

        return result.stdout
    except Exception as e:
        return str(e)


# Helper Functions
def list_files_in_repo(repo_path):
    repo_files = []
    for root, dirs, files in os.walk(repo_path):
        for file in files:
            repo_files.append(os.path.join(root, file))
    return repo_files


def read_file_content(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='latin-1') as file:
                return file.read()
        except UnicodeDecodeError:
            print(f"Skipping file {file_path} due to encoding issues.")
            return None


def call_openai_llm(prompt):
    try:
        context = summary_memory.load_memory_variables({})
        response = client.chat.completions.create(
            messages=[
                {"role": "assistant", "content": f"You are a code reader agent. Context so far:\n\n{context}\n\n"},
                {"role": "user", "content": prompt}
            ],
            model="gpt-4o",
            temperature=0.7,
            stream=False
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        return f"Error calling OpenAI API: {e}"


def summarize_file_content(file_path, content, file_structure):
    prompt = f""
    file structure from the project root
    $$
    {file_structure}
    $$\n\n
    Summarize the following content from the file **{file_path}**\n
    Content:\n
    ##{content}##\n\n

    Provide a concise summary capturing the main components, the role of this file in the project, and any key functions or classes it contains.
    ""
    return call_openai_llm(prompt)


def analyze_file_content(file_path, content, file_structure):
    prompt = f""
    file structure from the project root
    $$
    {file_structure}
    $$\n\n
    Analyze the following code from **{file_path}**:\n

    Content of the file\n
    !!!{content}!!!

    Please provide a detailed analysis with the foloowing details: \n
    1. file summary - max in a paragraphs.\n
    2. Dependency: based on the project structure, tell me the files its importing from.\n
    3. if any classes, then classes name with one line summary of functioning and code snippet.\n
    4. if any functions, then functions name with one line summary of functioning and code snippet.\n
    5. if any components, then names with the one line summary of functioning. and code snippet\n
    6. if any schemas, then names with fields and code snippets.\n
    8. if any contants, then list them all with one line summary.\n
    7. any security concerns.\n
    ""
    return call_openai_llm(prompt)


def read_ignore_patterns(repo_path):
    ignore_files = ['.gitignore', '.dockerignore']
    ignore_patterns = []

    for ignore_file in ignore_files:
        ignore_file_path = os.path.join(repo_path, ignore_file)
        if os.path.exists(ignore_file_path):
            with open(ignore_file_path, 'r') as file:
                for line in file:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        ignore_patterns.append(line)
    return ignore_patterns


def should_ignore_file(file_path, ignore_patterns):
    for pattern in ignore_patterns:
        if fnmatch.fnmatch(file_path, pattern) or pattern in file_path:
            return True
    return False


def determine_connections(file_contents):
    connections = {}
    for path, content in file_contents.items():
        connections[path] = []
        for other_path in file_contents:
            if other_path != path and os.path.basename(other_path) in content:
                connections[path].append(other_path)
    return connections


def output_analysis(file_analysis, file_connections):
    for path, analysis in file_analysis.items():
        print(f"File: {path}")
        print(f"Description: {analysis}")
        if file_connections[path]:
            print("Connected to:")
            for connection in file_connections[path]:
                print(f"  - {connection}")
        print("\n")

def run_code_reader(repo_path, output_file_path):
    # Main Logic
    local_files = list_files_in_repo(repo_path)
    ignore_patterns = read_ignore_patterns(repo_path)
    files_to_ignore_patterns = [
        '*.png', 'static', 'data.json', '__pycache__', 'db.sqlite3',
        'venv*', '.env', '.idea', '.git', '*.txt', '*.mp3',
        '.DS_Store', 'node_modules', '.next', '*.ttf', '*.jpeg', '*.svg', '*.ico', '*.woff', '*.d.ts'
    ]
    ignore_patterns.extend(files_to_ignore_patterns)

    file_contents = {}
    for file in local_files:
        if should_ignore_file(file, ignore_patterns):
            continue
        content = read_file_content(file)
        if content:
            file_contents[file] = content

    file_analysis = {}
    tree_output = get_filtered_tree(repo_path)

    print(tree_output)
    with open(output_file_path, 'w') as output_file:
        output_file.write(f"This project file structure: \n{tree_output}\n\n")
        output_file.write("-------------------------------------------\n\n")

        for path, content in file_contents.items():
            # Print the captured output
            print("preocessing file: " + path )
            # print(path, )
            summary = summarize_file_content(path, content,tree_output)
            summary_memory.save_context({"input": path}, {"output": summary})
            analysis = analyze_file_content(path, content,tree_output)
            file_analysis[path] = analysis

            output_file.write(f"This File: {path}\n")
            output_file.write(f"Summary or Overview of the file {path}:\n{summary}\n")
            output_file.write(f"Content of the file {path}:\n```code\n{content}\n```\n")
            output_file.write(f"Analysis of the file {path}:\n{analysis}\n\n")
            output_file.write("-------------------------------------------\n\n")

    file_connections = determine_connections(file_contents)
    output_analysis(file_analysis, file_connections)

# Usage
repo_path = '/Users/aman/PycharmProjects/pythonProject/executor'
output_file_path = 'output2.txt'
run_code_reader(repo_path, output_file_path)
    """
    # User query
    user_query = f"""
    use the following code as reference and create an django application for me with sqlite db. 
    \n```{code}```
    \n\n\n\n\n
    now i want you to save the path, summary, content and analysis in db for each file in a project.
    and we can have multiple projects, so each file table should have an association with user and project.
    Create login api for user. and apis to be able to create porjects also
    and use the above code for the main logic of the extracting the code and save in database. 
    
       
    Notes: 
    # Dont change the syntax of the code i provided you.
    # And you are already connected to terminal and at the working directory . \n
    # Ignore the node_modules, .gitignore, .next, venv, vevn2  . \n
    # in end step, add a step of asking user if he wants to do anything else?
    # "use 'python3 -m venv venv' to create a new environment. \n
    # you will need django rest framework and be mindful of editing the installed_apps.. \n
    # Use sqlite database only.
    
     """
    # use 'source venv2/bin/activate' to activate the environment. \n

    # user_query = (
    #     """
    #     you are in the working directory and are already connected to a terminal at working directory.
    #
    #     """
    # )


    # where you need to create new project, in django only.. \n

    # Initialize and run the workflow
    initial_state = AgentState(
        user_query=user_query,
        plan=[],
        current_step=0,
        execution_result=None,
        feedback=[],
        success=False,
        current_directory=directory,
        session_name=session_name,
    )

    # Run the state graph
    try:
        graph.invoke(initial_state, config={"recursion_limit": 100})
    except Exception as e:
        print(f"Error during workflow execution: {e}")

if __name__ == "__main__":
    main()

def call_executor(directory, user_request, project_obj, BASE_DIR, reference_file=''):
    WORKING_DIRECTORY = directory
    print("project_obj: ")
    print(project_obj)
    try:
        os.chdir(WORKING_DIRECTORY)
        print(f"Changed working directory to: {os.getcwd()}")
    except Exception as e:
        print(f"Failed to change directory: {e}")
        exit(1)

    if platform.system() != 'Darwin':
        print("This script uses AppleScript to open a new Terminal window and is only compatible with macOS.")
        return

    # Set the working directory
    directory = WORKING_DIRECTORY
    _, session_name = start_tmux_session_with_logging(directory, project_obj.name)

    # === Create and Compile Workflow ===
    workflow = StateGraph(AgentState)
    workflow.set_entry_point("planner")
    workflow.add_node("planner", planner)
    workflow.add_node("executor", executor)
    workflow.add_node("feedback_analyzer", feedback_analyzer)
    # workflow.add_node("completion_check", completion_check)
    workflow.add_edge("planner", "executor")
    workflow.add_edge("executor", "feedback_analyzer")
    # workflow.add_edge("feedback_analyzer", "completion_check")
    workflow.add_conditional_edges(
        "feedback_analyzer",
        completion_check,
        path_map={
            "executor": "executor",
            END: END,

        }
    )
    # Compile the graph
    graph = workflow.compile()

    # User query
    user_query = f"""
            User Request:\n{user_request}\n\n
            Notes:\n
            # General Conditions:\n
            # - Dont change the syntax of the code i provided you.\n
            # - You are already connected to terminal and at the working directory.\n
            # - Use sqlite database only.\n
            # - Ignore the following directories: node_modules, .gitignore, .next, venv, venv2.\n
            # You dont have to use only django or nextjs, use any framework or any language to achieve the task in best way possible, of your choice.\n 
            \n
            But if you decide to use Django and Next keep these things in mind\n
            \n
            # Backend (Django):\n
            #   Creating/Setup:\n
            #     - Always add django rest framework and corsheader and allow connections from localhost:3000.\n
            #     - Be mindful of editing the installed_apps in settings.\n
            #     - (Optional) 'use "python3 -m venv venv" to create a new environment.'\n
            #   Execution/Updating:\n
            #     - use 'source venv2/bin/activate' to activate the environment.\n

            # Frontend (Next.js):\n
            #   Creating/Setup:\n
            #     - (No explicit creation steps mentioned, just ensure to keep frontend structure intact.)\n
            #   Execution/Updating:\n
            #     - Ignore directories related to Next.js build outputs, such as .next.\n

    """
    # After completing all steps, ask the user: "Do you want to do anything else?"\n

    # "use 'python3 -m venv venv' to create a new environment. \n
    # you will need django rest framework and be mindful of editing the installed_apps.. \n

    # user_query = (
    #     """
    #     you are in the working directory and are already connected to a terminal at working directory.
    #
    #     """
    # )

    # where you need to create new project, in django only.. \n

    # Initialize and run the workflow
    initial_state = AgentState(
        user_query=user_query,
        plan=[],
        current_step=0,
        execution_result=None,
        feedback=[],
        success=False,
        current_directory=directory,
        session_name=session_name,
        project_id=str(project_obj.id),
        project_summary=project_obj.summary,
        reference_file=reference_file
    )

    # Run the state graph
    try:
        graph.invoke(initial_state, config={"recursion_limit": 100})
    except Exception as e:
        print(f"Error during workflow execution: {e}")
    print("finished with graph\n\n\n")


    try:
        os.chdir(BASE_DIR)
        print(f"Changed working directory to: {os.getcwd()}")
    except Exception as e:
        print(f"Failed to change directory: {e}")
        exit(1)


    flag = True
    while flag:
        user_input = input(f"Do you want to kill the tmux session '{session_name}'? (yes/no): ").strip().lower()
        if user_input in ["yes", "y"]:
            killed = kill_tmux_session(session_name)
            flag = not killed
        elif user_input in ["no", "n"]:
            print(f"The tmux session '{session_name}' was not killed.")
            flag = False
        else:
            print("Invalid input. Please enter 'yes' or 'no'.")
    kill_tmux_session(session_name)

    return "done"