import os
import time
from typing import List
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from openai import OpenAI as OpenAIClient  # 👈 Aliased to prevent any Pydantic clash
from daytona import Daytona, CreateSandboxFromSnapshotParams

load_dotenv()

# Instantiate the official OpenAI SDK client
openai_client = OpenAIClient(api_key=os.getenv("OPENAI_API_KEY"))

# Pydantic schema for output parsing
class RepoRequirements(BaseModel):
    summary: str = Field(description="Summary of tech stack and required background services")
    services_needed: List[str] = Field(description="List of services needed (e.g., Elasticsearch, Postgres, Redis)")
    build_tool: str = Field(description="Main build tool/package manager (e.g., npm, pip, maven)")

class SetupCommands(BaseModel):
    commands: List[str] = Field(
        description="Ordered list of Bash terminal commands to set up dependencies and spin up docker services"
    )

def analyze_repo_requirements(repo_url: str) -> RepoRequirements:
    print(f"🤖 [Analyst AI]: Analyzing infrastructure requirements for {repo_url}...")

    prompt = f"Analyze the GitHub repository at {repo_url}. Identify all background infrastructure services."

    # Use .beta.chat.completions.parse for Pydantic structured output
    response = openai_client.beta.chat.completions.parse(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are an expert DevOps analyst."},
            {"role": "user", "content": prompt}
        ],
        response_format=RepoRequirements,
    )

    report = response.choices[0].message.parsed
    return report

# ------------------------------------------------------------------
# 3. AI Stage 2: Setup Command Generator AI (Using openai_client)
# ------------------------------------------------------------------
def generate_setup_commands(requirements: RepoRequirements) -> SetupCommands:
    print("🤖 [Setup AI]: Generating terminal setup commands for Daytona environment...")

    prompt = f"""
    Given the following technical requirements for a sandbox environment:
    - Summary: {requirements.summary}
    - Services Needed: {', '.join(requirements.services_needed)}
    - Build Tool: {requirements.build_tool}

    Generate an ordered list of Linux Bash commands to set up this environment in a Daytona sandbox.
    Use `docker run -d` commands to start any necessary background services (e.g., Elasticsearch, Postgres, Redis).
    Do NOT run background applications that hang the shell (use `nohup` or background flags where applicable).
    """

    response = openai_client.beta.chat.completions.parse(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are an expert system administrator generating bash setup scripts."},
            {"role": "user", "content": prompt}
        ],
        response_format=SetupCommands,
    )

    commands_obj = response.choices[0].message.parsed
    print(f"✅ [Setup AI]: Generated {len(commands_obj.commands)} setup commands.")
    return commands_obj
# ------------------------------------------------------------------
# 4. Daytona Execution & Replication Engine
# ------------------------------------------------------------------

def provision_and_replicate(commands: List[str]):
    # Initialisation du client Daytona
    daytona = Daytona()
    
    # --- Étape A : Provisionnement de la Sandbox Master ---
    print("\n🚀 Creating Master Sandbox...")
    # On utilise un snapshot par défaut comme "daytona-small"
    master_params = CreateSandboxFromSnapshotParams(snapshot="daytona-small") 
    master_sandbox = daytona.create(master_params) 
    master_id = master_sandbox.id 
    
    print(f"⚙️ Executing setup script on Master Sandbox ({master_id})...")
    for cmd in commands:
        print(f"  👉 Running: {cmd}")
        # Passage sous forme de dictionnaire structuré
        res = master_sandbox.process.exec({"command": cmd})
        print(f"  Output:\n{res.result}")

    print("✅ Master Sandbox successfully configured!")

    # --- Étape B : Duplication sur 2 nouvelles Sandboxes ---
    replica_sandboxes = []
    print("\n👯 Replicating configured environment across 2 new sandboxes...")
    
    for i in range(1, 3):
        print(f"🚀 Provisioning Replica {i}...")
        replica_sandbox = daytona.create(CreateSandboxFromSnapshotParams(snapshot="daytona-small")) 
        replica_sandboxes.append(replica_sandbox)
        
        print(f"📋 Syncing setup commands to replica {replica_sandbox.id}...") 
        for cmd in commands:
            replica_sandbox.process.exec(cmd) 
            
        print(f"✅ Replica {replica_sandbox.id} ready!") 

    print("\n🎉 Pipeline Complete! Active Daytona Sandboxes:")
    print(f" 📍 Master:  `daytona code {master_id}`")
    for r in replica_sandboxes:
        print(f" 📍 Replica: `daytona code {r.id}`") 

# ------------------------------------------------------------------
# Execution Entry Point
# ------------------------------------------------------------------
if __name__ == "__main__":
    TARGET_REPO = "https://github.com/fastapi/full-stack-fastapi-template"

    # Stage 1: AI analyzes what the repo needs
    # repo_reqs = analyze_repo_requirements(TARGET_REPO)
    # print(repo_reqs)

    # Stage 2: AI writes the setup terminal commands
    # setup_cmds = generate_setup_commands(repo_reqs)
    # print("commands:")
    # print(setup_cmds)
    commands= ['sudo apt-get update -y', 'sudo apt-get install -y docker.io', 'sudo apt-get install -y docker-compose', 'sudo systemctl start docker', 'sudo systemctl enable docker', 'sudo usermod -aG docker $USER', 'newgrp docker', '', '# Pull required Docker images', 'docker pull postgres:latest', 'docker pull redis:latest', 'docker pull traefik:latest', '# For a more extended setup including Celery, pulling a Python base image might be needed', 'docker pull python:3.9-slim', '# Create a Docker network to allow containers to communicate', 'docker network create sandbox-net', '', '# Start Postgres in detached mode with environment variables', 'docker run -d --name postgres --network sandbox-net \\', '  -e POSTGRES_USER=sandbox_user \\', '  -e POSTGRES_PASSWORD=sandbox_pass \\', '  -e POSTGRES_DB=sandbox_db \\', '  postgres:latest', '', '# Start Redis in detached mode', 'docker run -d --name redis --network sandbox-net redis:latest', '', '# Start Traefik with a simple configuration for routing, using a mounted configuration file', 'echo "\nentryPoints:\n  web:\n    address: ":80"\n  websecure:\n    address: ":443"" > traefik.toml', 'docker run -d --name traefik --network sandbox-net \\', '  -v $PWD/traefik.toml:/etc/traefik/traefik.toml \\', '  -p 80:80 -p 443:443 \\', '  traefik:latest', '', '# Create a simple Docker Compose file for the application stack', 'echo "version: \'3.9\'\\nservices:\\n  backend:\\n    image: python:3.9-slim\\n    depends_on:\\n      - postgres\\n      - redis\\n    volumes:\\n      - .:/app\\n    working_dir: /app\\n    command: uvicorn main:app --host 0.0.0.0 --port 8000\\n    networks:\\n      - sandbox-net\\n  frontend:\\n    image: node:14\\n    volumes:\\n      - ./frontend:/frontend\\n    networks:\\n      - sandbox-net\\n  celery:\\n    image: celery:latest\\n    networks:\\n      - sandbox-net\\nnetworks:\\n  sandbox-net:\\n    external: true" > docker-compose.yml', '', '# Spin up application services using Docker Compose', 'docker-compose up -d']

    # Stage 3: Setup Master Sandbox & replicate across 2 extra sandboxes
    provision_and_replicate(commands)