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


def main():
    description = "An open-source self-hosted Notion alternative with markdown support and kanban boards"
    
    print("1. Querying OpenAI to extract search keywords...")
    # queries = ['open-source Notion alternative', 'self-hosted markdown kanban', 'markdown kanban board app'] 
    queries = repo_search(description)
    print(f"Generated Queries: {queries}")

    
if __name__ == "__main__":
    main()