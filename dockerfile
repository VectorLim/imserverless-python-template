# Override with --build-arg BASE_IMAGE=<compatible IMServerless Python base>.
ARG BASE_IMAGE=amr-registry.caas.intel.com/soia/icmpcs-soims:base
FROM ${BASE_IMAGE}
USER root
WORKDIR /app
ENV ENV_MODE=test \
    SCRIPT_NAME=example \
    FUNCCONF=/etc/icmpcs/conf \
    ENVFUNCAPPLOC=/app \
    PYTHONPATH=/app
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt
COPY config/func.json /etc/icmpcs/conf/func.json
COPY main.py /app/main.py
COPY pipeline /app/pipeline
CMD ["funchost_controller"]
