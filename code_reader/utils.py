import ast
import os
import fnmatch
import subprocess
import time
import base64

from dotenv import load_dotenv

load_dotenv()

from openai import OpenAI
from langchain.memory import ConversationSummaryBufferMemory
from langchain.chains.summarize import load_summarize_chain
from langchain_openai import ChatOpenAI
from code_reader.models import File, Project
from django.conf import settings

# Initialize OpenAI and memory
client = OpenAI(api_key=settings.OPEN_AI_KEY)
llm = ChatOpenAI(model='gpt-4o', temperature=0.7, api_key=settings.OPEN_AI_KEY)
llm_mini = ChatOpenAI(model='gpt-4o-mini', temperature=0.4, api_key=settings.OPEN_AI_KEY)
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
            ".next|node_modules|.git|venv|venv2|venv3|__pycache__|postgres_data|static|.idea|media|dist|build|*.log|*.tmp",
            # Exclude more unnecessary items
            "-a",  # Include hidden files and directories
            "--noreport",  # Exclude summary info (e.g., file count) to keep the output clean
            "--dirsfirst",  # Display directories before files
            "-f",  # Show full paths for files and directories
            directory  # Target directory
        ]
        # Execute the command and capture the output
        print(" ".join(command))
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print(result)
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
            model="gpt-4o",
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
            model=model,
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
    Provide a concise summary capturing the main components, the role of this file in the project, and any key functions or classes it contains. Also what are the import and export
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


def run_file_summarizer(project_id, file_path):
    project = Project.objects.get(id=project_id)
    # Main Logic
    file_content = read_file_content(file_path)
    tree_output = get_filtered_tree(project.repo_path)
    project.tree_structure = tree_output
    project.save()
    summary = summarize_file_content(file_path, file_content, tree_output)
    #FIXME: removing analysis, as we are not using it anywhere for now
    # analysis = analyze_file_content(file_path, file_content, tree_output)
    file_obj, created = File.objects.get_or_create(
        path=file_path,
        project=project,
        defaults={'analysis': summary, "summary": summary, "content": file_content}
    )
    if not created:
        file_obj.analysis = summary
        file_obj.summary = summary
        file_obj.content = file_content
        file_obj.save()
    return file_obj

def run_code_reader(project):
    """First time reading the project"""
    # Main Logic
    repo_path = project.repo_path

    local_files = list_files_in_repo(repo_path)
    ignore_patterns = read_ignore_patterns(repo_path)
    # files_to_ignore_patterns = [
    #     '*.png', 'static', '*.json', '__pycache__', 'db.sqlite3', '.idea', '*.xlsx', 'media',
    #     'venv*', '.env', '.idea/', '.git', '*.txt', '*.mp3', '/static/', '/postgres_data/',
    #     '.DS_Store', 'node_modules', '.next', '*.ttf', '*.jpeg', '*.svg', '*.ico', '*.woff', '*.d.ts'
    # ]
    files_to_ignore_patterns = [
        '*.png',  # Image files
        '*.jpeg',  # Image files
        '*.svg',  # Image files
        '*.ico',  # Icons
        '*.ttf',  # Fonts
        '*.woff',  # Fonts
        '*.xlsx',  # Excel files
        '*.txt',  # Plain text files
        '*.json',  # JSON files
        '*.d.ts',  # TypeScript declaration files
        '*.log',  # Log files
        '*.lock',  # Lock files (e.g., package-lock.json, yarn.lock)
        '*.ipynb',  # Jupyter notebooks
        '*.zip',  # Zip archives
        '*.tar.gz',  # Tarball archives
        'static',  # Static directory
        'staticFilesgit ',  # Static directory
        'media',  # Media directory
        '__pycache__',  # Python cache
        '.pytest_cache',  # Pytest cache
        '.mypy_cache',  # mypy cache
        '.DS_Store',  # macOS filesystem metadata
        'Thumbs.db',  # Windows image cache file
        'db.sqlite3',  # SQLite database
        'coverage',  # Coverage directory or files
        'coverage*',  # Any coverage-related files (e.g., coverage.xml)
        '.env',  # Environment files
        'venv*',  # Virtual environments (venv, venv2, etc.)
        '.idea',  # IDE (JetBrains) config
        '.vscode',  # VSCode config
        '.git',  # Git repository data
        'node_modules',  # Node.js dependencies
        '.next',  # Next.js build output
        '.idea/',  # Redundant IDE config folder reference
        '/static/',  # Another form of static path reference
        '/postgres_data/'  # PostgreSQL data directory
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

    file_analysis = {}
    tree_output = get_filtered_tree(repo_path)
    project.tree_structure = tree_output
    project.save()
    print(tree_output)
    for path, _ in file_contents.items():
        print(path)

    # important condition for the history to be saved in project summary.
    if 'history' in project.summary:
        project_summary_till_now = ast.literal_eval(project.summary)
        if 'history' in project_summary_till_now:
            summary_memory.save_context({"input": "code_reading history till now"}, {"output": project_summary_till_now["history"]})

    for path, content in file_contents.items():
        # Print the captured output
        print("preocessing file: " + path)
        file_object = File.objects.filter(path=path, project=project).first()
        # print(file_object.content)
        # print(content)
        if file_object and file_object.content == content:
            print(f"file {file_object.path} skipped")
            continue
        # print(path, )
        summary = summarize_file_content(path, content, tree_output)
        summary_memory.save_context({"input": path}, {"output": summary})
        # FIXME: not using analyze_file_content for now, so replacing it with summary.
        # analysis = analyze_file_content(path, content, tree_output)
        file_analysis[path] = summary
        file_obj, created = File.objects.update_or_create(
            path=path,
            project=project,
            defaults={'analysis': summary, "summary": summary, "content": content}
        )
        if created:
            print("File " + path + " created.")
        else:
            print("File "+ path + " updated.")

        project.summary = summary_memory.load_memory_variables({})
        project.save()


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

