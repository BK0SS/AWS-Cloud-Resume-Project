# I rebuilt my resume as a serverless AWS app — here's the architecture and what I learned

*Cross-post-ready draft for Dev.to / Medium / Hashnode. Replace the screenshots/links marked `<<>>` before publishing.*

---

When I started transitioning into cloud engineering, I kept reading the same advice: **don't just collect certs — build things.** So I took on the [Cloud Resume Challenge](https://cloudresumechallenge.dev) and shipped my résumé as a fully serverless, fully automated AWS application.

This post walks through the architecture, the four problems that actually slowed me down, and the lessons I'm taking into the next project.

**Live site:** <<https://your-cloudfront-domain.cloudfront.net>>
**Source:** <<https://github.com/your-handle/cloud-portfolio>>

## The architecture in one picture

![Architecture diagram](../docs/architecture.png)

Two halves:

- **Edge & hosting** — the static HTML/CSS/JS lives in a private S3 bucket. CloudFront sits in front with HTTPS and an Origin Access Control policy, so the bucket itself is never publicly reachable.
- **Serverless backend** — a single Python Lambda behind HTTP API Gateway increments a counter in DynamoDB and returns the new value. The frontend calls it on page load.

Both halves are defined in one `template.yaml` (AWS SAM) and deployed by GitHub Actions over OIDC — no long-lived AWS keys live in my repo.

## Why these choices

| Decision | Why |
|---|---|
| **S3 + CloudFront** (vs. Amplify Hosting) | I wanted to see and own every piece — bucket policy, OAC, cache behaviors. |
| **HTTP API** (vs. REST API) | Cheaper, faster, and the visitor counter doesn't need request validation or API keys. |
| **AWS SAM** (vs. Terraform) | Tightest integration with Lambda; `sam build`, `sam deploy`, `sam logs` is a great local loop for serverless. |
| **OIDC** (vs. access keys) | Best-practice for GitHub→AWS, and once the OIDC provider exists, every future repo is a 30-second setup. |
| **DynamoDB on-demand** | I have no idea what traffic looks like, and one counter row never justifies provisioned capacity. |

## The four problems that actually took time

### 1. CORS

The frontend fetches the API from a CloudFront origin; the API lives at an `execute-api` URL. Different origins → CORS preflight.

What worked:

- HTTP API: set `CorsConfiguration.AllowOrigins` in the SAM template.
- Lambda: return CORS headers on **every** response, including errors and the OPTIONS preflight.

The trap: I had CORS configured on the API but my Lambda was throwing on the first call (empty table), so API Gateway returned a 502 *without* CORS headers — and the browser blamed CORS instead of the 502. Always check the network tab's raw response, not just the console error.

### 2. CloudFront + S3 with OAC

The newer pattern (Origin Access Control) replaced OAI. It needs:

1. An OAC resource on the distribution.
2. A bucket policy that allows `s3:GetObject` only when `AWS:SourceArn` equals the distribution ARN.

That creates a chicken-and-egg in IaC — the bucket policy references the distribution, the distribution references the bucket. SAM/CloudFormation handles it because both resources are in one stack, but the first `sam deploy` does the dance for you.

### 3. Atomic counter

Naive version:

```python
item = table.get_item(Key={"id": "site"})["Item"]
table.put_item({"id": "site", "count": item["count"] + 1})
```

Two concurrent invocations and you've lost a vote. The right move:

```python
table.update_item(
    Key={"id": "site"},
    UpdateExpression="ADD #c :inc",
    ExpressionAttributeNames={"#c": "count"},
    ExpressionAttributeValues={":inc": 1},
    ReturnValues="UPDATED_NEW",
)
```

`ADD` is atomic, creates the attribute if it doesn't exist, and removes the read-modify-write race entirely.

### 4. IAM for GitHub Actions

I started with an access key in a GitHub secret. Then I read [the AWS docs on OIDC](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services) and switched. The setup is:

1. Create one OIDC provider in IAM (per AWS account, not per repo).
2. Create a deploy role whose trust policy is conditional on `repo:OWNER/REPO:*`.
3. In the workflow, use `aws-actions/configure-aws-credentials@v4` with `role-to-assume`.

The `Condition` block in the trust policy is the *whole* security model. Get the `sub` claim wrong and either nothing works or — worse — too much works.

## Testing the Lambda without AWS

I used [moto](https://github.com/getmoto/moto) to mock DynamoDB:

```python
@pytest.fixture
def app_module(monkeypatch):
    monkeypatch.setenv("TABLE_NAME", "VisitorCounter-Test")
    with mock_aws():
        boto3.resource("dynamodb").create_table(...)
        import backend.src.app as app
        importlib.reload(app)
        yield app
```

The `importlib.reload` matters — `app.py` reads env vars at import time. If you don't reload after setting the env vars, you'll test against the wrong table name.

These tests run on every PR in GitHub Actions before SAM is even invoked.

## What I'd do next

- **Custom domain + ACM** — pick up `bogdankosulin.dev` and use Route 53 + ACM in `us-east-1` (CloudFront requires the cert there).
- **Tighten the deploy role.** I started with `PowerUserAccess` to get unblocked; I want a least-privilege inline policy scoped to the stack's resources.
- **Add WAF in front of the API** — even a single counter endpoint can be abused; AWS-managed rule groups are a one-liner.
- **Instrument with CloudWatch RUM** for real frontend metrics.

## Takeaways for anyone starting

1. **Use IaC from day one.** Click-ops feels faster for the first 30 minutes and slower for the rest of your life.
2. **CI/CD before "polish."** Wiring up GitHub Actions early forces you to fix permissions and config the *right* way; otherwise you'll discover everything was hand-tweaked the day you need to redeploy.
3. **Read the raw HTTP responses.** Browser console messages and CloudFront error pages both lie about which layer actually broke.

If you're working through the same challenge, my repo is here: <<https://github.com/your-handle/cloud-portfolio>>. Issues and PRs welcome.

---

*Bogdan Kosulin is a Thompson Rivers University alum transitioning into cloud and software engineering. Find him on [LinkedIn](<<linkedin-url>>).*
