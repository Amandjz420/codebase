# executor/agent_functions.py

import os
from typing import TypedDict, Optional, List, Union, Literal
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain.memory import ConversationSummaryBufferMemory
from langgraph.graph import END

from code_reader.executor.outputparser import PlannerResponse

from code_reader.executor.tools import code_editor, terminal_executor, need_user_input, update_file_summary, read_file_content, \
    search_web_browser, update_project_root_dir_and_tree_structure, starting_new_tmux_session_for_running_service, wait_for_some_time
from code_reader.executor.utils import llm, invoke_model
from code_reader.models import Project


# Define Agent State
class AgentState(TypedDict):
    user_query: str
    plan: List[dict]
    current_step: int
    execution_result: Optional[str]
    feedback: []
    success: bool
    current_directory: str
    session_name: str
    project_id: str
    project_summary: str
    reference_file: str

# Initialize memory
summary_memory = ConversationSummaryBufferMemory(
    llm=llm,
    max_token_limit=300,
)
summary_memory.output_key = "Executor"
summary_memory.input_key = "Planner"

tools_info = """
    - code_editor: Use this to create or modify code files. 
      Inputs are the relative 'filepath' and 'instructions' on how to modify the code.
      Always verify you are using the correct relative path from the current working directory.
      If there is any uncertainty about the file location or the filepath, 
      either infer the correct path from context or ask the user for clarification.\n

    - terminal_executor: Use this to execute terminal commands. Input should be the command to run.\n

    - need_user_input: Use this when you need the user to provide additional information or clarification.
      Explain clearly why you need their input.\n
      
    - search_web_browser: Use this only when you want to browse the web browser. 
                give useful query to search for as a param. Also always ask user permission 
                before using search_web_browser tool.\n
    
    - update_project_root_dir_and_tree_structure: use this tool to update the repo_path and tree_structure of the project,
                once you create new project in any framework like django, nextjs, flask, etc.
                You just have to pass the project_id and abosolute path of the newly created project in params.\n
    
    - starting_new_tmux_session_for_running_service: use this tool to run a service in a new tmux, 
        so that you can do testing on it. This tool will recieve the current project_id and command to run the service.
    
    - wait_for_some_time: use this tool to wait whenever you have to wait for something to complete. give the time in second 
        you would like to wait and reason for the wait
    
    - update_file_summary: Use this to summarize or update the summary in database for a file in the project.
      Inputs are `project_id` (string) and `absolute_file_path`.
      Make sure you provide the correct `project_id` and a valid `absolute_file_path`.
      This will update and return the summary of the file in the database.
      Always run this tool for all the files that got commited. \n
      
    - read_file_content: Use this tool to read the contents of any file in the project. You have to just provide
     the relative file path, based on current working directory.
    
    Notes -\n
      Use update_project_root_dir_and_tree_structure only just after creating a new project using any framework.\n 
      If you plan to use search_web_browser tool, ask user's permission once before that, using the need_user_input tool\n
      Except while committing git changes, do not use the tool for updating file summary unless the user explicitly requests it.\n"
"""

def get_plan_title_array(plan):
    plan_title_array = []
    for step in plan:
        plan_title_array.append(step["title"])
    return plan_title_array

def planner(state: AgentState) -> AgentState:
    project_summary = state.get("project_summary", "")
    user_query = state.get("user_query", "")
    prompt = (
        f"The user wants the following to be done:\n\n"
        f"**User Query:**\n##{user_query}##\n\n"
        "Your task:\n"
        "1. Break down the user's requested task into a detailed sequence of steps to achieve the given goal.\n"
        "2. Each step should be described in simple, clear language without omitting any crucial information.\n"
        "3. If the user query references specific files or paths, use these exact paths in the steps.\n"
        "4. Ensure the steps are detailed enough so that the executor agent, using its available tools, "
        "can follow them without additional assumptions.\n\n"
        # "After completing the main steps:\n"
        # "- Include a step to use `git status` to review which files have changed.\n"
        # "- Then prompt the user to decide if they want to commit these changes.\n"
        # "- If they choose to commit, include steps to summarize and store the updated information for each changed file using the appropriate tool.\n"
        "Available tools for execution (for reference):\n"
        f"{tools_info}\n\n"
        "Additional context:\n"
        f"**Project Summary:** {project_summary}\n\n"
    )

    response = invoke_model(prompt, PlannerResponse)
    # response = invoke_model(prompt, PlannerResponse)
    response_dict = response.model_dump()

    plan = response_dict['steps']
    while True:
        print(plan)
        for i in range(len(plan)):
            print(f"Step {i+1}: {plan[i]['title']}")
            print(f"Flow of planning: {plan[i]['psuedo_code']}")
            # plan.append(response["steps"][i])
        user_feedback = input("Does the plan look correct? (yes/no): ")
        if user_feedback.lower() == 'yes':
            break
        elif user_feedback.lower() == 'no':
            feedback = input("Please provide feedback on what needs to be changed: ")
            prompt = (
                f"The user provided the following feedback on the plan:\n\n"
                f"User's Feedback on Plan:\n##{feedback}##\n\n"
                f"User's Query:\n##{user_query}##\n\n"
                f"Previous Plan:\n##{str(plan)}##\n\n"
                "Update the plan based on the user's feedback. Make sure to:\n"
                "- Keep the steps clear, detailed, and aligned with the user's goal.\n"
                "- If multiple files are mentioned in one step, split them into separate steps so each file is handled individually.\n"
                "- Maintain the requirement not to use tools to update file information before committing changes, unless explicitly requested.\n"
                "- Continue to provide a sequence of steps that the executor can follow without assumptions.\n\n"
                "Do not omit any crucial information needed to achieve the user's objectives.\n"
            )
            response = invoke_model(prompt, PlannerResponse, image=state.get("reference_file", ""))
            plan = response.model_dump()['steps']
        else:
            print("Invalid input. Please enter 'yes' or 'no'.")

    state.update({
        "plan": plan,
        "current_step": 0,
        "success": False
    })
    return state

def executor(state: AgentState) -> AgentState:
    plan = state["plan"]
    current_step = state["current_step"]

    if current_step < len(plan):
        step_description = plan[current_step]
        print(f"\nExecuting Step {current_step + 1}/{len(plan)}: {str(step_description)}\n")

        tools = [code_editor, terminal_executor, need_user_input, update_project_root_dir_and_tree_structure,
                 update_file_summary, search_web_browser, starting_new_tmux_session_for_running_service,
                 wait_for_some_time, read_file_content]

        summary_var = summary_memory.load_memory_variables({})
        if 'history' in summary_var:
            summary = summary_var.get('history')
        else:
            summary = str(summary_var)

        # print("summary =========================>")
        # print(summary)
        project = Project.objects.get(id=int(str(state['project_id'])))
        tree_structure = "not available right now in db, will be updated soon."
        if len(project.tree_structure) > 5:
            tree_structure = project.tree_structure
        # Updated tool descriptions in the system prompt
        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "I am an AI assistant that helps execute steps provided by the user using the tools available to me.\n\n"
                "I always keep in mind the initial user request: ``{user_query}``\n"
                "Until now, the summary of the previous execution is:\n##{summary}##\n"
                "Project's current working directory: ``" + state['current_directory'] + "``\n"
                "Project's tree structure: \n``" + tree_structure + "``\n"
                "Current's project id: ``" + state['project_id'] + "``\n"
                "Available tools:\n``" + tools_info + "``\n"
                "My goal is to successfully execute the given steps by appropriately using these tools.\n"
                "When the user provides a step description, determine the necessary actions and use the tools to perform them.\n"
                "**Important:** I always carefully verify the correct relative paths when using the code_editor tool. "
                "If I will be unsure about the file location or name, i ll ask the user for clarification before making any changes.\n"
                "Will also provide a clear explanation for each action I take.\n"
                "Also stop asking user, what else can be done. just reply with execution results and what happened.\n\n"
            ),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])

        agent = create_tool_calling_agent(llm, tools, prompt)
        agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
        result = agent_executor.invoke(
            {"input": f"{str(step_description)}", "summary": summary, "user_query": state["user_query"]}
        )
        print("Agent Result:", result['output'])
        # print("Current working directory", os.getcwd())
        # Store the execution result in the state
        execution_result = result
        if len(state["feedback"]) > 4:
            state["feedback"] = (state["feedback"][:4] +
                                 [{f"Step_{current_step}": result['input'], "execution_result_by_agent": result['output']}])
        else:
            state["feedback"].append({f"step_{current_step}": result['input'], "execution_result_by_agent": result['output']})
        state['execution_result'] = str(execution_result)
        state['current_directory'] = os.getcwd()

        summary_memory.save_context({"Planner": f"{step_description['title']}"}, {"Executor": execution_result['output']})
    else:
        print("All steps have been executed.")
    return state

def feedback_analyzer(state: AgentState) -> AgentState:
    print("Feedback Analyzer ")
    execution_result = state.get("execution_result", "")
    current_step = state.get("current_step", 0)
    plan = state.get("plan", [])

    if not execution_result:
        execution_result = "No execution result available."
        # Decide whether to halt or proceed; for now, proceed to the next step
        state["current_step"] = current_step + 1
        return state

    # Retrieve the step description
    if current_step < len(plan):
        step_description = plan[current_step]
    else:
        step_description = "Unknown step."
    summary_var = summary_memory.load_memory_variables({})
    if 'history' in summary_var:
        summary = summary_var.get('history')
    else:
        summary = str(summary_var)
    # print("summary =========================>")
    # print(summary)

    plan_titles = get_plan_title_array(plan)
    # Construct the prompt to analyze the execution result and determine if additional steps are needed
    prompt = (
        f"User Given Task: ``{state['user_query']}``\n\n"
        "Below is the current context and progress summary:\n"
        f"Execution Summary till now:\n##{summary}##\n\n"
        f"The result of last 4 executions were:\n##``{str(state['feedback'])}``##\n"
        f"Current Working Directory: ``{state['current_directory']}``\n\n"
        "Please analyze the following details to assess whether the current task step was successfully completed:\n\n"
        f"**Previous Steps Descriptions:** ##{str(plan_titles[:current_step])}##\n"
        f"Request and results of few Previous Executions:\n##{str(state['feedback'])}##\n\n"
        f"**Current Step Description:** ##{step_description}##\n"
        f"**Current Step Execution done by Agent:** ##{execution_result}##\n\n"
        "After reviewing the current step, consider the upcoming steps:\n"
        f"##{str(plan[current_step + 1:])}##\n\n"
        "Your goal:\n"
        "1. Determine if the current step has been successfully completed, also check based on the last executing what we are going to do next is right or not.\n"
        "2. If additional actions or modifications are needed before proceeding, propose new steps or modifications.\n\n"
        "If you deem that new steps are required, please rewrite the remaining plan to include these new steps without missing any crucial information from the upcoming steps.\n\n"
        "Important Note:\n"
        "- If the planner suggests processing multiple files in one single step, break that step down so that the executor processes one file at a time in separate steps.\n"
        "- Do not use tool for updating file information before committing changes based on the user input, unless the user query explicitly requests it.\n"
        "- If you are stuck in some problem and you are not able to solve it,try using search_web_browser tool to find solution.\n"
        "- If user want you to stop the execution of the plan, then remove all the steps and pass empty plan.\n"
        
        # "- Always check if user was asked whether to git commit the changes in the end atleast once.\n\n"
        "\n\n"
        "The Steps will be executed using an executor agent with the following tools:\n"
        f"``{tools_info}``\n\n"
        "Please provide a clear, logically reasoned assessment and, if necessary, an updated plan."
    )

    response = invoke_model(prompt, PlannerResponse)
    print("Feedback Analyzer Response:", response.model_dump())

    further_steps = response.model_dump().get("steps", [])
    print("Upcoming Steps: ")
    print("\n".join(get_plan_title_array(further_steps)))
    if further_steps:
        # Insert the additional steps into the plan after the current step
        plan = plan[:current_step + 1] + further_steps
        state["plan"] = plan

    state["current_step"] = current_step + 1
    return state

def completion_check(state: AgentState) -> Union[str, Literal[END]]:
    current_step = state.get("current_step", 0)
    plan = state.get("plan", [])

    # Check if all steps have been executed
    if current_step >= len(plan):
        print("All steps have been completed.")
        return END
    else:
        # There are more steps to execute
        return "executor"