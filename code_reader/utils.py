import ast
import os
import fnmatch
import subprocess
import time
import base64
from pathlib import Path

from dotenv import load_dotenv
import tiktoken
import PyPDF2

load_dotenv()

from openai import OpenAI
from groq import Groq
from langchain.memory import ConversationSummaryBufferMemory
from langchain.chains.summarize import load_summarize_chain
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from code_reader.models import File, Project
from django.conf import settings

# Initialize OpenAI and memory
# client = OpenAI(api_key=settings.OPEN_AI_KEY)
client = Groq(
    api_key=settings.GROQ_AI_KEY,  # This is the default and can be omitted
)
# llm = ChatOpenAI(model='gpt-4o', temperature=0.7, api_key=settings.OPEN_AI_KEY)
# llm_mini = ChatOpenAI(model='gpt-4o-mini', temperature=0.4, api_key=settings.OPEN_AI_KEY)
llm = ChatGroq(
    model="llama3-70b-8192",  # Specify the desired model
    temperature=0.7,             # Adjust the temperature as needed
    api_key=settings.GROQ_AI_KEY,             # Set the maximum number of tokens
    timeout=60,                  # Set a timeout for API requests
    max_retries=3                # Define the number of retries for failed requests
)
llm_mini = ChatGroq(
    model="llama-3.1-8b-instant",  # Specify the desired model
    temperature=0.7,             # Adjust the temperature as needed
    api_key=settings.GROQ_AI_KEY,             # Set the maximum number of tokens
    timeout=60,                  # Set a timeout for API requests
    max_retries=3                # Define the number of retries for failed requests
)
summary_memory = ConversationSummaryBufferMemory(llm=llm, max_token_limit=500)
summary_maker_chain = load_summarize_chain(llm=llm_mini, chain_type='map_reduce', token_max=10000)

def get_filtered_tree(directory):
    """
    Runs the 'tree' command with exclusions and captures the output in a variable.

    Args:
    directory (str): The directory to run the tree command on. Defaults to the current directory.

    Returns:
    str: The output of the tree command.
    """
    try:
        # Command to run `tree` with exclusions
        command = [
            "tree",
            "-L", "4",  # Limit to 4 levels
            "-I",
            ".next|node_modules|.git|venv|venv2|venv3|__pycache__|postgres_data|static|.idea|media|dist|build|*.log|*.tmp|public|__MACOSX",
            "-a",  # Include hidden files and directories
            "--noreport",  # Exclude summary info (e.g., file count) to keep the output clean
            "--dirsfirst",  # Display directories before files
            directory  # Target directory
        ]
        # Execute the command and capture the output
        print(" ".join(command))
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print(result)
        return result.stdout
    except Exception as e:
        return str(e)


def calculate_token_count(text, model="gpt-4o"):
    """
    Calculate the number of tokens in the given text using tiktoken.

    :param text: The content of the file as a string.
    :param model: The model for which to calculate tokens (e.g., 'gpt-4').
    :return: The token count.
    """
    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(text))


# Helper Functions
def list_files_in_repo(repo_path):
    repo_files = []
    for root, dirs, files in os.walk(repo_path):
        for file in files:
            repo_files.append(os.path.join(root, file))
    return repo_files

def list_folders_in_repo(repo_path):
    """
    Recursively lists all folders in the given repository path.

    :param repo_path: Path to the repository.
    :return: A list of folder paths.
    """
    folder_paths = []
    for root, dirs, files in os.walk(repo_path):
        for dir_name in dirs:
            folder_paths.append(os.path.join(root, dir_name))
    return folder_paths


def read_file_content(file_path, token_limit=6000):
    """
    Reads the content of a file and ensures it doesn't exceed the token limit.

    :param file_path: Path to the file.
    :param token_limit: Maximum allowed token count.
    :return: File content if within token limit, otherwise None.
    """
    try:
        content = ""
        if file_path.lower().endswith('.pdf'):
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    content += page.extract_text()
        else:
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='latin-1') as file:
                content = file.read()
        except UnicodeDecodeError:
            print(f"Skipping file {file_path} due to encoding issues.")
            return None

    # Calculate tokens
    token_count = calculate_token_count(content)
    if token_count > token_limit:
        divider = int(token_count / token_limit) + 1
        print(f"File {file_path} exceeds token limit ({token_count} tokens). Splitting into {divider} parts.")
        # Split the content into `divider` parts
        part_size = len(content) // divider
        parts = [content[i:i + part_size] for i in range(0, len(content), part_size)]
        return f"Sample content of the file {file_path} due to token count ({token_count}) exceeding limit ({token_limit}).\n\n" + parts[0]

    return content


def call_openai_llm_with_image(prompt, base64_image):
    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "assistant", "content": f"You are an helpful assistant. and you try your best to help the user. "
                                                 f"Understand what is in the file and help the user. \n"},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]}
            ],
            model="gpt-4o",
            temperature=0.7,
            stream=False
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        return f"Error calling OpenAI API: {e}"


def call_openai_llm_without_memory(prompt):
    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "assistant", "content": f"You are an helpful assistant. and you try your best to help the user\n"},
                {"role": "user", "content": prompt}
            ],
            model="o3-mini",
            temperature=0.7,
            stream=False
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        return f"Error calling OpenAI API: {e}"



def call_openai_llm(prompt, model="gpt-4o"):
    try:
        summary_var = summary_memory.load_memory_variables({})
        if 'history' in summary_var:
            context = summary_var.get('history')
        else:
            context = str(summary_var)
        response = client.chat.completions.create(
            messages=[
                {"role": "assistant", "content": f"You are a code reader agent. Context so far:\n\n{context}\n\n"},
                {"role": "user", "content": prompt}
            ],
            model='llama-3.1-8b-instant',
            temperature=0.7,
            stream=False
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        return f"Error calling OpenAI API: {e}"


def summarize_file_content(file_path, content, file_structure):
    prompt = f"""
    file structure from the project root
    $$
    {file_structure}
    $$\n\n
    Summarize the following content from the file **{file_path}**\n
    Content:\n
    ##{content}##\n\n
    Provide a concise summary capturing the main components, 
    the role of this file in the project, 
    any key functions or classes it contains, and
    also note import of the related files in the project.
    """
    return call_openai_llm(prompt, model='gpt-4o-mini')


def analyze_file_content(file_path, content, file_structure):
    prompt = f"""
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
    5. if any components, then names with the one line summary of functioning for each and code snippet\n
    6. if any schemas, then names with fields and code snippets.\n
    7. if any contants, then list them all with one line summary.\n
    8. if frontend framework, mention the page navigation based on component clicks or processing.\n
    9. any security concerns.\n
    """
    return call_openai_llm(prompt, 'gpt-4o-mini')


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


def output_analysis(file_analysis, file_connections):
    for path, analysis in file_analysis.items():
        print(f"File: {path}")
        print(f"Description: {analysis}")
        if file_connections[path]:
            print("Connected to:")
            for connection in file_connections[path]:
                print(f"  - {connection}")
        print("\n")


def run_file_summarizer(project_id, file_path, updated_code=False):
    project = Project.objects.get(id=project_id)
    # Main Logic
    file_content = read_file_content(file_path)
    tree_output = get_filtered_tree(project.repo_path)
    project.tree_structure = tree_output
    project.save()
    summary = summarize_file_content(file_path, file_content, tree_output)

    parent_path = Path(file_path).parent
    if parent_path == project.repo_path:
        parent_file = None
    else:
        parent_file = File.objects.filter(project=project, path=parent_path).first()
    # Get the parent file if it exists

    #FIXME: removing analysis, as we are not using it anywhere for now
    # analysis = analyze_file_content(file_path, file_content, tree_output)
    file_obj, created = File.objects.get_or_create(
        path=file_path,
        project=project,
        defaults={
            'analysis': summary,
            "summary": summary,
            "content": file_content,
            "updated_code": file_content if updated_code else None,
            "parent_file": parent_file if parent_file else None,
        }
    )
    if not created:
        file_obj.analysis = summary
        file_obj.summary = summary
        file_obj.content = file_content
        if updated_code:
            file_obj.updated_code = file_content if updated_code else None
        file_obj.save()
    return file_obj


def run_code_reader(project, execution_creation_files=False):
    """First time reading the project"""
    # Main Logic
    repo_path = project.repo_path

    local_files = list_files_in_repo(repo_path)
    local_folders = list_folders_in_repo(repo_path)
    ignore_patterns = read_ignore_patterns(repo_path)

    files_to_ignore_patterns = [
        '*.png', 'static/', 'staticFiles/', '__MACOSX/', '__pycache__', 'db.sqlite3', '.idea', '*.xlsx',
        'venv/', 'venv2/', 'venv3/', '.env', '.idea/', '.git', '*.mp3', 'static/', 'postgres_data/', 'public/', '.vite/',
        '.DS_Store', 'node_modules/', '.next/', '*.ttf', '*.jpeg', '*.svg', '*.ico', '*.woff', '*.d.ts'
    ]
    ignore_patterns.extend(files_to_ignore_patterns)

    file_contents = {}
    # print(ignore_patterns)
    for file in local_files:
        # print(file)
        if should_ignore_file(file, ignore_patterns):
            continue
        content = read_file_content(file)
        if content:
            file_contents[file] = content
    final_folders = []
    for folder in local_folders:
        # print(file)
        if should_ignore_file(folder, ignore_patterns):
            continue
        # content = read_file_content(folder)
        final_folders.append(folder)
    print(final_folders)
    file_analysis = {}
    tree_output = get_filtered_tree(repo_path)
    project.tree_structure = str(tree_output)
    project.save()
    print(tree_output)
    for path, _ in file_contents.items():
        print(path)

    # important condition for the history to be saved in project summary.
    if 'history' in project.summary:
        project_summary_till_now = ast.literal_eval(project.summary)
        if 'history' in project_summary_till_now:
            summary_memory.save_context({"input": "code_reading history till now"}, {"output": project_summary_till_now["history"]})

    for folder_path in final_folders:
        print(f"Processing folder: {folder_path}")

        # Check if the folder is already in the database
        folder_object = File.objects.filter(path=folder_path, project=project).first()

        # If the folder is already processed, skip it
        if folder_object:
            print(f"Folder {folder_object.path} skipped")
            continue

        parent_folder_path = Path(folder_path).parent
        if parent_folder_path == Path(repo_path):
            parent_folder = None
        else:
            parent_folder = File.objects.filter(path=str(parent_folder_path), project=project).first()
        folder_structure = get_filtered_tree(folder_path)
        folder_obj, created = File.objects.update_or_create(
            path=folder_path,
            project=project,
            defaults={
                'analysis': '',
                'summary': '',
                'content': str(folder_structure),  # Folders may not have content
                'parent': parent_folder,
                'is_file_type': False  # Assuming this field distinguishes between files and folders
            }
        )
        if created:
            print(f"Folder {folder_obj.path} created successfully")

    for path, content in file_contents.items():
        # Print the captured output
        print("preocessing file: " + path)
        file_object = File.objects.filter(path=path, project=project).first()

        if file_object and file_object.updated_code:
            file_object.updated_code = None
            file_object.save()

        if file_object and file_object.content == content:
            print(f"file {file_object.path} skipped")
            continue


        # print(path, )
        summary = summarize_file_content(path, content, tree_output)
        summary_memory.save_context({"input": path}, {"output": summary})
        # FIXME: not using analyze_file_content for now, so replacing it with summary.
        # analysis = analyze_file_content(path, content, tree_output)
        file_analysis[path] = summary

        parent_path = Path(path).parent
        if parent_path == Path(repo_path):
            parent_file = None
        else:
            print(f"parent path: {parent_path}")
            parent_file = File.objects.filter(path=str(parent_path), project=project).first()
            if not parent_file:
                File.objects.create(path=path,project=project, is_file_type=False)

        file_obj, created = File.objects.update_or_create(
            path=path,
            project=project,
            defaults={
                'analysis': summary,
                'summary': summary,
                'content': content,
                'parent': parent_file
            }
        )
        if execution_creation_files:
            file_obj.updated_code = file_obj.content
            file_obj.save()


        if created:
            print("File " + path + " created.")
        else:
            print("File "+ path + " updated.")

        project.summary = summary_memory.load_memory_variables({})
        project.save()


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def build_tree(node):
    """
    Recursively builds a dictionary representing the file/folder hierarchy.

    :param node: The current File instance.
    :return: A dictionary representing the node and its children.
    """
    # Determine the type and file extension
    node_type = 'file' if node.is_file_type else 'folder'
    file_extension = node.path.split('.')[-1] if node.is_file_type else 'none'

    # Base structure of the node
    tree_node = {
        'name': node.path.split('/')[-1],  # Extract the name from the path
        'type': node_type,
        'filetype': file_extension,
        'id': node.id,
        'updated':  True if node.updated_code and node_type == 'file' else False
    }

    # # Include content for files
    # if node.is_file_type:
    #     tree_node['content'] = node.content

    # Recursively add children if the node is a folder
    if not node.is_file_type:
        children = node.children.all()
        tree_node['children'] = [build_tree(child) for child in children]

    return tree_node