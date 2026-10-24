# SketchForge – AWS Lambda container image
# Base: AWS official Python 3.11 Lambda runtime (ECR public gallery).
# Reference: https://gallery.ecr.aws/lambda/python
#
# Build:
#   docker build -t sketchforge-lambda .
#
# Local smoke-test:
#   docker run -p 9000:8080 sketchforge-lambda
#   curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" \
#        -H "Content-Type: application/json" \
#        -d '{"image_b64": "<base64_jpeg>"}'
#
# Push to ECR (replace ACCOUNT_ID and REGION):
#   aws ecr get-login-password | docker login --username AWS \
#       --password-stdin ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com
#   docker tag sketchforge-lambda:latest \
#       ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com/sketchforge-lambda:latest
#   docker push ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com/sketchforge-lambda:latest

FROM public.ecr.aws/lambda/python:3.11

# ---------------------------------------------------------------------------
# 1. System-level build dependencies for OpenCV headless
#    (libGL is NOT needed for opencv-python-headless; libgthread is pulled by
#    GLib which Pillow links against on Amazon Linux 2023).
# ---------------------------------------------------------------------------
RUN dnf install -y --setopt=install_weak_deps=False \
        libgomp \
        mesa-libGL \
    && dnf clean all

# ---------------------------------------------------------------------------
# 2. Python dependencies
#    Pinned to ensure reproducible competition submissions.
#    opencv-python-headless>=5.0.0 is the primary competition deliverable.
# ---------------------------------------------------------------------------
COPY requirements-lambda.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements-lambda.txt

# ---------------------------------------------------------------------------
# 3. SketchForge source (installed in editable mode is not available inside
#    Lambda; install as a regular package instead).
# ---------------------------------------------------------------------------
COPY src/ ${LAMBDA_TASK_ROOT}/src/
COPY pyproject.toml ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir --no-deps ${LAMBDA_TASK_ROOT}/

# ---------------------------------------------------------------------------
# 4. Lambda handler
# ---------------------------------------------------------------------------
COPY deploy/aws/lambda_function.py ${LAMBDA_TASK_ROOT}/

# The Lambda runtime expects the handler in the form <module>.<function>.
CMD ["lambda_function.handler"]
