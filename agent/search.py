import os
import json
from dotenv import load_dotenv
from openai import OpenAI
from daytona import Daytona, CreateSandboxFromSnapshotParams

load_dotenv()

# 1. Initialize OpenAI Client (automatically reads OPENAI_API_KEY from env)
openai_client = OpenAI()

# 2. Initialize Daytona Client
daytona = Daytona()

def repo_search(app_description: str) -> list[str]:
    """Uses OpenAI to convert a text description into structured GitHub search queries."""
    prompt = f"""
    Given the app description: "{app_description}"
    Search me 3 github repo that respect that description or solve the problem
    Return ONLY a valid raw JSON array of strings, e.g.: ["query1", "query2", "query3"]
    """
    
    # Generate structured JSON using gpt-4o-mini
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    
    content = response.choices[0].message.content.strip()
    data = json.loads(content)
    
    # Extract array if model returned a dictionary wrapper like {"queries": [...]}
    if isinstance(data, dict):
        return next(iter(data.values()))
    return data

def search_repo_in_daytona(queries: list[str]) -> str:
    """Provisions a Daytona sandbox to execute search queries against GitHub API."""
    
    print("Creating Daytona sandbox container...")
    # daytona.create() retourne une instance de Sandbox [1]
    sandbox = daytona.create(CreateSandboxFromSnapshotParams(
        env_vars={"DEBUG": "true", "LOG_LEVEL": "info"},
    ))
    
    try:
        query_str = "+".join(queries.split())
        cmd = f'curl -s "https://api.github.com/search/repositories?q={query_str}&sort=stars&order=desc" | grep -E "\\"full_name\\"|\\"html_url\\"|\\"stargazers_count\\"|\\"description\\"" | head -n 4'
        
        print(f"Executing search in Daytona for query: '{queries}'")
        # Utilisation de sandbox.process.exec pour exécuter la commande [2]
        execution = sandbox.process.exec(cmd)
        
        # Le résultat textuel est récupéré dans l'attribut .result [3]
        return execution.result
    finally:
        print("Cleaning up Daytona sandbox...")
        # Suppression de la sandbox pour libérer les ressources [4]
        sandbox.delete()


def main():
    description = "An open-source self-hosted Notion alternative with markdown support and kanban boards"
    
    print("1. Querying OpenAI to extract search keywords...")
    # queries = ['open-source Notion alternative', 'self-hosted markdown kanban', 'markdown kanban board app'] 
    queries = repo_search(description)
    print(f"Generated Queries: {queries}")

    
    # if queries:
    #     print("\n2. Executing repository lookup in Daytona...")
    #     repo_info = search_repo_in_daytona(queries)
    #     print("\n--- Best Matching Repository ---")
    #     print(repo_info)

if __name__ == "__main__":
    main()