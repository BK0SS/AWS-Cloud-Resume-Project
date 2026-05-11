# Runbook — Cloud Resume on AWS

End-to-end setup, from a fresh AWS account to a deployed site with CI/CD.
**Estimated time:** 2–3 hours the first time. **Estimated cost:** under $1/month at typical resume traffic (most services stay inside the AWS Free Tier).

---

## Phase 1 — AWS account hardening

> Never deploy with the root user. Everything below uses an IAM user with MFA, then OIDC for CI/CD.

### 1.1 Sign up and lock down root

1. Create the AWS account at <https://aws.amazon.com>.
2. Sign in as root → **Security credentials** → enable **MFA** on the root user (use an authenticator app, not SMS).
3. Delete any root access keys if they exist.

### 1.2 Billing safety net

1. **Billing → Billing preferences** → enable **Receive Free Tier usage alerts** and **Receive billing alerts**.
2. **CloudWatch → Alarms → Create alarm** → metric `EstimatedCharges` (region: `us-east-1` — this is where AWS publishes the metric). Threshold `> $5`. Add an SNS subscription to your email.
3. **AWS Budgets → Create budget** → monthly cost budget at $10 with alerts at 80% and 100%.

### 1.3 Create an admin IAM user (for one-time setup)

1. **IAM → Users → Create user** named `admin-bk` → attach AWS-managed policy `AdministratorAccess`.
2. Enable MFA on this user.
3. Create an access key for **CLI access only** — store it in `~/.aws/credentials` under a named profile (e.g. `[cloud-resume]`).

```bash
aws configure --profile cloud-resume
# default region us-west-2
```

---

## Phase 2 — Local toolchain

Install once on your dev machine:

```bash
# macOS
brew install awscli aws-sam-cli python@3.12 git

# Ubuntu / WSL
sudo apt install -y python3.12 python3-pip git unzip
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscli.zip
unzip awscli.zip && sudo ./aws/install
pip install aws-sam-cli
```

Verify:

```bash
aws --version
sam --version
python3 --version
```

---

## Phase 3 — First deploy (local)

Clone this repo, then:

```bash
cd cloud-portfolio
# Run tests
pip install -r backend/requirements-dev.txt
python -m pytest backend/tests/ -v

# Build & deploy
cd infra
sam build
sam deploy --guided --profile cloud-resume
# Accept defaults; stack name = cloud-resume; region = us-west-2.
```

`sam deploy --guided` saves your answers in `samconfig.toml`. Subsequent deploys are just `sam deploy`.

### 3.1 Wire the frontend to the API

After the deploy succeeds, copy the `VisitorCounterApiUrl` output:

```
Key                 VisitorCounterApiUrl
Value               https://abc123xyz.execute-api.us-west-2.amazonaws.com/visitors
```

Open `frontend/js/main.js` and replace the placeholder:

```js
const API_ENDPOINT = "https://abc123xyz.execute-api.us-west-2.amazonaws.com/visitors";
```

### 3.2 Upload the site

```bash
# From repo root
SITE_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name cloud-resume \
  --query "Stacks[0].Outputs[?OutputKey=='SiteBucketName'].OutputValue" \
  --output text --profile cloud-resume)

aws s3 sync frontend/ "s3://$SITE_BUCKET/" --delete --profile cloud-resume
```

Grab the CloudFront URL from the `CloudFrontDomainName` output and open it. The first request can take 1–2 minutes while the distribution warms up.

---

## Phase 4 — GitHub Actions (OIDC, no static keys)

Best practice: GitHub authenticates to AWS using OpenID Connect. No `AWS_ACCESS_KEY_ID` secrets in your repo.

### 4.1 Create the OIDC provider in AWS

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 \
  --profile cloud-resume
```

### 4.2 Create the deploy role

Save as `trust-policy.json` (replace `YOUR_ACCOUNT_ID` and `YOUR_GH_USER/YOUR_REPO`):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Federated": "arn:aws:iam::YOUR_ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com" },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": { "token.actions.githubusercontent.com:aud": "sts.amazonaws.com" },
      "StringLike": { "token.actions.githubusercontent.com:sub": "repo:YOUR_GH_USER/YOUR_REPO:*" }
    }
  }]
}
```

```bash
aws iam create-role --role-name github-cloud-resume-deploy \
  --assume-role-policy-document file://trust-policy.json \
  --profile cloud-resume

# Scope down later; for the challenge, broad managed policies are fine.
aws iam attach-role-policy --role-name github-cloud-resume-deploy \
  --policy-arn arn:aws:iam::aws:policy/PowerUserAccess --profile cloud-resume
aws iam attach-role-policy --role-name github-cloud-resume-deploy \
  --policy-arn arn:aws:iam::aws:policy/IAMFullAccess --profile cloud-resume
```

> **Tighten later.** Once everything works, replace these managed policies with a least-privilege inline policy scoped to your stack's resources (S3 bucket, CloudFormation stack, Lambda function, DynamoDB table, CloudFront distribution).

### 4.3 Add the role ARN to GitHub

Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Name                  | Value                                                           |
|-----------------------|-----------------------------------------------------------------|
| `AWS_DEPLOY_ROLE_ARN` | `arn:aws:iam::YOUR_ACCOUNT_ID:role/github-cloud-resume-deploy`  |

### 4.4 Push and watch it deploy

```bash
git add .
git commit -m "feat: initial cloud resume"
git push origin main
```

Watch the workflows under the **Actions** tab. `backend.yml` runs pytest then `sam deploy`. `frontend.yml` syncs `frontend/` to S3 and invalidates the CloudFront cache.

---

## Phase 5 — Day-2 operations

| Task                                    | Command                                                       |
|----------------------------------------|---------------------------------------------------------------|
| View live logs                         | `sam logs -n VisitorCounterFunction --stack-name cloud-resume --tail` |
| Invalidate CDN cache manually          | `aws cloudfront create-invalidation --distribution-id DIST_ID --paths "/*"` |
| Tail DynamoDB items                    | `aws dynamodb scan --table-name cloud-resume-visitors`        |
| Delete everything                      | `sam delete --stack-name cloud-resume`                        |

---

## Common gotchas

- **CORS errors in the browser.** Either the `AllowedOrigin` parameter doesn't match your CloudFront domain, or the Lambda response is missing CORS headers. Both are handled in `app.py` and `template.yaml` — but once you have a stable CloudFront URL, redeploy with `--parameter-overrides AllowedOrigin=https://dxxxx.cloudfront.net` to tighten it.
- **403 from CloudFront.** The bucket policy condition uses the distribution ARN; if you ever recreate the distribution, the old condition won't match. Redeploy the stack rather than the bucket policy alone.
- **`sam deploy` complains about IAM capabilities.** Make sure your CLI command (or the GitHub workflow) passes `--capabilities CAPABILITY_IAM`.
- **CloudFront cache shows stale HTML.** Either wait 5 minutes, or push again — the frontend workflow runs `cloudfront create-invalidation /*` on every deploy.
- **OIDC role assume fails.** The `sub` condition in the trust policy must match `repo:OWNER/REPO:*`. Typos here are the #1 cause of GitHub Actions failures.
- **Lambda cold starts.** Acceptable for a visitor counter (~300 ms on Python 3.12 / 128 MB). If it ever matters, bump memory to 512 MB.
