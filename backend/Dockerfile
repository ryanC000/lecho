# Python 3.12 to match the project venv (3.12.4) — the wheel availability that
# ticket 03 depends on (parselmouth, scipy, psycopg, noisereduce) was verified
# against cp312, so the base image must not drift ahead of it.
#
# x86_64 ONLY. praat-parselmouth 0.4.7 publishes Linux wheels for i686 and
# x86_64 and no aarch64 wheel at any Python version, so an ARM64 host (e.g.
# Oracle's free tier) would have to build Praat's C++ from source. numpy,
# scipy, psycopg-binary and noisereduce all ship aarch64 wheels; parselmouth
# alone is the constraint. See phase3-deploy ticket 05 before picking a host.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Fail the build, not the first request, if a wheel is missing for this platform.
# parselmouth is the fragile one (it does not publish for every architecture);
# the rest are here because a source build of scipy/psycopg on a slim image
# would fail at runtime in a much less obvious way. faster_whisper is checked
# because the content gate fails *open* — a missing wheel would not raise at
# runtime, it would silently disable the gate.
RUN python -c "import parselmouth, numpy, scipy, noisereduce, psycopg, boto3, faster_whisper"

# Pre-download the STT model (~140MB) so a worker pod does not fetch it from
# HuggingFace on its first job — that turns a cold start into a timeout, and a
# scaled-up Deployment into N simultaneous downloads.
ENV HF_HOME=/opt/models
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"

COPY . ./

EXPOSE 8000

# Default entrypoint is the API. The worker is the same image with the command
# overridden (compose service / k8s Deployment): one build, two roles.
#   python -m worker.main
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
