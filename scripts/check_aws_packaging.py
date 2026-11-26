"""Offline checks for the RetailAI container/ECR/ECS reference artifacts.

Safe to run with no cloud account, credentials or Docker daemon.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check_packaging() -> None:
    aws_dir = ROOT / "infra" / "aws"
    api = json.loads((aws_dir / "ecs" / "api-task-definition.template.json").read_text())
    web = json.loads((aws_dir / "ecs" / "frontend-task-definition.template.json").read_text())
    for name, task, port in (("api", api, 8000), ("frontend", web, 3000)):
        assert task["requiresCompatibilities"] == ["FARGATE"], name
        assert task["networkMode"] == "awsvpc", name
        assert int(task["cpu"]) >= 256 and int(task["memory"]) >= 512, name
        assert task["executionRoleArn"].startswith("arn:aws:iam::REPLACE_ACCOUNT_ID:role/"), name
        assert len(task["containerDefinitions"]) == 1, name
        c = task["containerDefinitions"][0]
        assert c["portMappings"][0]["containerPort"] == port, name
        assert c["logConfiguration"]["logDriver"] == "awslogs", name
        assert ":sha-REPLACE_COMMIT_SHA12" in c["image"], name
        assert not any("PASSWORD" in x["name"] or "API_KEY" in x["name"] for x in c["environment"]), name
        assert "REPLACE_ACCOUNT_ID" in c["image"], name

    api_container = api["containerDefinitions"][0]
    assert {s["name"] for s in api_container["secrets"]} == {"DATABASE_URL", "GROQ_API_KEY"}
    assert all("secretsmanager:" in s["valueFrom"] for s in api_container["secrets"])
    assert api_container["healthCheck"]["command"][0] == "CMD-SHELL"
    web_environment = {x["name"]: x["value"] for x in web["containerDefinitions"][0]["environment"]}
    assert web_environment["DEMO_UI_ENABLED"] == "false", "Demo tokens must never be exposed publicly"
    assert not any("DEMO_" in x["name"] and x["name"] != "DEMO_UI_ENABLED" for x in web["containerDefinitions"][0]["environment"])

    iam_dir = aws_dir / "iam"
    for file in iam_dir.glob("*.json"):
        policy = json.loads(file.read_text())
        assert policy["Version"] == "2012-10-17", file.name
        assert policy["Statement"], file.name
    trust = json.loads((iam_dir / "github-ecr-oidc-trust.template.json").read_text())
    condition = trust["Statement"][0]["Condition"]["StringEquals"]
    assert condition["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com"
    assert condition["token.actions.githubusercontent.com:sub"].endswith(":environment:ecr-publish")
    ecr = json.loads((iam_dir / "github-ecr-publish-policy.template.json").read_text())
    assert all(not a.startswith("ecs:") for stmt in ecr["Statement"] for a in stmt["Action"])

    workflow = (ROOT / ".github" / "workflows" / "publish-ecr.yml").read_text()
    for required in ("workflow_dispatch:", "id-token: write", "configure-aws-credentials", "amazon-ecr-login", "docker push", "npm run typecheck", "python -m pytest", "github.ref == 'refs/heads/main'", "environment: ecr-publish"):
        assert required in workflow, required
    for forbidden in ("aws ecs update-service", "aws ecs create-service", "aws ecs register-task-definition", "AWS_SECRET_ACCESS_KEY"):
        assert forbidden not in workflow, forbidden

    dockerignore = (ROOT / ".dockerignore").read_text().splitlines()
    assert ".env" in dockerignore
    assert ".retailai_storage" in dockerignore
    frontend_ignore = (ROOT / "frontend" / ".dockerignore").read_text().splitlines()
    assert ".env.local" in frontend_ignore
    assert "USER retailai" in (ROOT / "Dockerfile").read_text()
    assert "USER node" in (ROOT / "frontend" / "Dockerfile").read_text()


def main() -> None:
    check_packaging()
    print("RetailAI AWS packaging smoke: PASS")
    print("ECR OIDC workflow, ECS task templates, IAM policies and Docker secrets: PASS")
    print("Offline check only: no AWS calls, image builds, or deployments")


if __name__ == "__main__":
    main()
