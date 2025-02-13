# executor/main.py

import os
import platform
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv
load_dotenv()

from code_reader.executor.agent_functions import planner, executor, feedback_analyzer, completion_check, AgentState
from code_reader.executor.utils import start_tmux_session_with_logging, kill_tmux_session, get_output_buffer


def call_executor(directory, user_request, project_obj, BASE_DIR, reference_file='', firebase_chat_id='', session_name=""):
    WORKING_DIRECTORY = directory
    print("project_obj: ")
    print(project_obj)
    try:
        os.chdir(WORKING_DIRECTORY)
        print(f"Changed working directory to: {os.getcwd()}")
    except Exception as e:
        print(f"Failed to change directory: {e}")
        exit(1)

    # if platform.system() != 'Darwin':
    #     print("This script uses AppleScript to open a new Terminal window and is only compatible with macOS.")
    #     return

    # Set the working directory
    directory = WORKING_DIRECTORY
    print("session_name: ", session_name)

    _, session_name = start_tmux_session_with_logging(directory, project_obj.name, session_name)
    print("session_name: ", session_name)
    output_buffer = get_output_buffer(session_name)
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
            User Request:\n```{user_request}```\n\n
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
        reference_file=reference_file,
        firebase_chat_id=firebase_chat_id,
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
    kill_tmux_session(session_name)

    return "done"


def call_executor_with_plan(directory, user_request, plan, project_obj, BASE_DIR, reference_file='', session_name='', firebase_chat_id=''):

    WORKING_DIRECTORY = directory
    print("project_obj: ")
    print(project_obj)
    try:
        os.chdir(WORKING_DIRECTORY)
        print(f"Changed working directory to: {os.getcwd()}")
    except Exception as e:
        print(f"Failed to change directory: {e}")
        exit(1)

    # if platform.system() != 'Darwin':
    #     print("This script uses AppleScript to open a new Terminal window and is only compatible with macOS.")
    #     return

    # Set the working directory
    directory = WORKING_DIRECTORY
    _, session_name = start_tmux_session_with_logging(directory, project_obj.name, session_name=session_name)

    # === Create and Compile Workflow ===
    workflow = StateGraph(AgentState)
    workflow.set_entry_point("executor")
    workflow.add_node("executor", executor)
    workflow.add_node("feedback_analyzer", feedback_analyzer)
    # workflow.add_node("completion_check", completion_check)
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
            User Request:\n```{user_request}```\n\n
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
    # where you need to create new project, in django only.. \n

    # Initialize and run the workflow
    initial_state = AgentState(
        user_query=user_query,
        plan=plan,
        current_step=0,
        execution_result=None,
        feedback=[],
        success=False,
        current_directory=directory,
        session_name=session_name,
        project_id=str(project_obj.id),
        project_summary=project_obj.summary,
        reference_file=reference_file,
        firebase_chat_id=firebase_chat_id,
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
    kill_tmux_session(session_name)
    return "done"