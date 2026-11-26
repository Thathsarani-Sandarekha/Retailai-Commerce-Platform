# AWS reference deployment configuration

The two `.template.json` task definitions and IAM policy samples are realistic handoff artifacts for an **intended** Fargate deployment—not claims of deployed AWS infrastructure.

## Services

| Component | Intended AWS resource | Code/config evidence |
| --- | --- | --- |
| API container | ECS Fargate task, private subnet, internal target group | `ecs/api-task-definition.template.json` |
| Web container | ECS Fargate task behind HTTPS ALB | `ecs/frontend-task-definition.template.json` |
| Container registry | Private Amazon ECR repositories | `.github/workflows/publish-ecr.yml` |
| Secrets | AWS Secrets Manager for RDS DSN and Groq API key | API task `secrets` array |
| Logs | CloudWatch Logs | Both tasks `awslogs` configuration |
| Private catalog images | S3, IAM task role | `iam/ecs-api-s3-policy.template.json` |
| Database | RDS PostgreSQL (future deployment) | SQLAlchemy URL via runtime secret; migration work follows |

The GitHub Actions OIDC role (image publisher) is **not** the ECS task role and is **not** the ECS task execution role. Keep them separate. The ECR publish role cannot create or update running ECS services.

Do **not** use the current local-demo identity tokens in a public frontend. The frontend task template intentionally disables the demo proxy. To complete a real deployment, introduce production authentication and server-side ownership controls, a production-ready API gateway, migrations and DB initialization, restricted network routing, TLS, health targets, alarms and backups. Replace the template placeholders only after those pieces exist.

See `RETAILAI_STEP3_AWS_SETUP.md` at repository root for local installation and optional manual ECR publishing instructions.
