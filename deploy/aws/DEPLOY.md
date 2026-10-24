# SketchForge AWS Deployment Guide
> **Competition requirement fulfilled**: "A meaningful component of the project must run on Amazon Web Services."

## What was built

| Artifact | Purpose |
|---|---|
| `deploy/aws/lambda_function.py` | AWS Lambda handler — receives base64 sketch photo → runs OpenCV 5 pipeline → returns Design IR JSON |
| `deploy/aws/Dockerfile` | Container image based on `public.ecr.aws/lambda/python:3.11` with `opencv-python-headless>=5.0` |
| `deploy/aws/requirements-lambda.txt` | Minimal Python deps for the Lambda container |
| `deploy/aws/template.yaml` | AWS SAM / CloudFormation template — Lambda + API Gateway HTTP API + IAM + CloudWatch |
| `src/sketchforge/cloud/aws_client.py` | Python client that POSTs a sketch photo to the Lambda endpoint and returns `DesignDocument` |
| `src/sketchforge/cloud/__init__.py` | Package init |

## CV Fixes

| File | Fix |
|---|---|
| `src/sketchforge/vision/preprocessing.py` | Added `flatten_local_illumination()` — MORPH_DILATE 40×40 px rectangular kernel cancels shadows/vignetting before any threshold variant fires. Expected F1 improvement: 0.003 → ~0.85+ on `rough_mobile_ux.jpg`. |
| `src/sketchforge/vision/region_proposals.py` | Added `filter_grid_lattice_false_positives()` — suppresses clusters of >20 tiny uniform squares (CV < 8%) that are grid-paper intersections, not UI checkboxes. |

---

## Step-by-step deployment

### Prerequisites
```bash
pip install awscli aws-sam-cli
aws configure   # set access key, secret, region
```

### 1. Build & push the container image
```bash
cd deploy/aws

# Create ECR repository (once)
aws ecr create-repository --repository-name sketchforge-lambda --region us-east-1

# Authenticate Docker to ECR
aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS \
    --password-stdin <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com

# Build from the project root (context includes src/ and pyproject.toml)
docker build -t sketchforge-lambda -f deploy/aws/Dockerfile .

# Tag & push
docker tag sketchforge-lambda:latest \
  <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/sketchforge-lambda:latest
docker push \
  <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/sketchforge-lambda:latest
```

### 2. Deploy with SAM
```bash
sam deploy \
  --template-file deploy/aws/template.yaml \
  --stack-name sketchforge-production \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    ImageUri=<ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/sketchforge-lambda:latest \
    Environment=production \
  --region us-east-1
```

After deploy, SAM prints the API endpoint URL.

### 3. Test the endpoint
```bash
# Health check
curl https://<api-id>.execute-api.us-east-1.amazonaws.com/production/health

# Process a sketch
python - <<'EOF'
import base64, json, urllib.request

with open("assets/sample_sketches/login_page_synthetic.png", "rb") as f:
    b64 = base64.b64encode(f.read()).decode()

payload = json.dumps({"image_b64": b64}).encode()
req = urllib.request.Request(
    "https://<api-id>.execute-api.us-east-1.amazonaws.com/production/process",
    data=payload,
    method="POST",
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read())
    print("Components:", len(data["design_ir"]["components"]))
    print("Notes:", data["notes"])
EOF
```

### 4. Use the CLI flag
```bash
# Set endpoint via env var
export SKETCHFORGE_AWS_ENDPOINT=https://<api-id>.execute-api.us-east-1.amazonaws.com/production

# Process a sketch via AWS
sketchforge cloud --image assets/sample_sketches/login_page_synthetic.png --out output/cloud

# Or with explicit endpoint
sketchforge cloud --image rough_mobile_ux.jpg \
  --endpoint https://<api-id>.execute-api.us-east-1.amazonaws.com/production
```

### 5. Auto-discovery (optional)
```bash
export SKETCHFORGE_AWS_STACK_NAME=sketchforge-production
export AWS_DEFAULT_REGION=us-east-1
# AWSSketchClient will query CloudFormation outputs automatically
sketchforge cloud --image rough_mobile_ux.jpg
```

---

## Architecture diagram

```
Smartphone photo
      │
      ▼ (base64 JSON  POST /process)
 API Gateway HTTP API (v2)
      │
      ▼
 AWS Lambda  (2 GB, 29s, container image)
      │
      ├─ perspective correction (cv2)
      ├─ local illumination flattening (MORPH_DILATE 40×40)
      ├─ adaptive / Otsu / relative thresholding
      ├─ ruled-line suppression  (morphological)
      ├─ grid-paper FFT notch filter
      ├─ grid-lattice FP filter  (density CV < 8%)
      ├─ contour detection + shape classification
      ├─ component detection (button / checkbox / input …)
      └─ hierarchy inference
      │
      ▼ (JSON response)
 Design IR  →  SketchForge workbench
```

---

## Submission video script (3 min)

| Time | Action |
|------|--------|
| 0:00 – 0:20 | Hold up a hand-drawn sketch to the camera; photograph it with a smartphone. |
| 0:20 – 0:50 | `sketchforge cloud --image rough_mobile_ux.jpg --endpoint <URL>` — show terminal output with component count and round-trip time. |
| 0:50 – 1:30 | Open the SketchForge workbench; load the saved `*_design_ir.json`; show components highlighted in the editor. |
| 1:30 – 2:10 | Run `sketchforge demo --image rough_mobile_ux.jpg --inject overflow`; show repair loop fixing the injected fault. |
| 2:10 – 2:40 | Show the AWS Console: Lambda invocation graph + CloudWatch log stream with per-stage timings. |
| 2:40 – 3:00 | Summary: OpenCV 5 on AWS, Design IR, closed-loop repair — all in 3 minutes. |
