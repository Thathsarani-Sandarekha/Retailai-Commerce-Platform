"""Prevent accidental regressions in portfolio cloud infrastructure templates."""
import json
from pathlib import Path

from scripts.check_aws_packaging import ROOT, check_packaging


def test_cloud_package_passes_offline_contract():
    check_packaging()


def test_api_task_uses_runtime_secret_references_not_plaintext():
    task = json.loads((ROOT / "infra/aws/ecs/api-task-definition.template.json").read_text())
    container = task["containerDefinitions"][0]
    assert {secret["name"] for secret in container["secrets"]} == {"DATABASE_URL", "GROQ_API_KEY"}
    assert "GROQ_API_KEY" not in {entry["name"] for entry in container["environment"]}


def test_frontend_reference_disables_public_demo_gateway():
    task = json.loads((ROOT / "infra/aws/ecs/frontend-task-definition.template.json").read_text())
    config = {item["name"]: item["value"] for item in task["containerDefinitions"][0]["environment"]}
    assert config["DEMO_UI_ENABLED"] == "false"
    assert "DEMO_STAFF_TOKEN" not in config
    assert "DEMO_MANAGER_TOKEN" not in config


def test_oidc_trust_restricted_to_protected_environment():
    policy = json.loads((ROOT / "infra/aws/iam/github-ecr-oidc-trust.template.json").read_text())
    condition = policy["Statement"][0]["Condition"]["StringEquals"]
    assert "environment:ecr-publish" in condition["token.actions.githubusercontent.com:sub"]
    assert condition["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com"


def test_ecr_publisher_cannot_create_or_update_ecs():
    policy = json.loads((ROOT / "infra/aws/iam/github-ecr-publish-policy.template.json").read_text())
    permissions = [action for stmt in policy["Statement"] for action in stmt["Action"]]
    assert all(action.startswith("ecr:") for action in permissions)
    assert "ecr:PutImage" in permissions


def test_cloud_reference_keeps_real_credentials_out_of_both_images():
    root_dockerignore = (ROOT / ".dockerignore").read_text()
    web_dockerignore = (ROOT / "frontend" / ".dockerignore").read_text()
    assert ".env\n" in root_dockerignore
    assert ".env.local\n" in web_dockerignore
