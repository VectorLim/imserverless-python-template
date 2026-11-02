# Repository-level GitHub Actions runner for .github/workflows/release.yml.
# Build and start it with runner/start-runner.ps1, which downloads and verifies cache/*.
ARG BASE_IMAGE=amr-registry.caas.intel.com/soia/icmpcs-soims:base
FROM docker:27-cli AS docker

FROM ${BASE_IMAGE}
COPY --from=docker /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker /usr/local/libexec/docker/cli-plugins/docker-buildx /usr/local/libexec/docker/cli-plugins/docker-buildx
COPY cache/kubectl /usr/local/bin/kubectl
COPY cache/actions-runner.tar.gz /tmp/actions-runner.tar.gz
RUN chmod 755 /usr/local/bin/kubectl \
    && mkdir /runner && tar xzf /tmp/actions-runner.tar.gz -C /runner && rm /tmp/actions-runner.tar.gz
WORKDIR /runner
ENV RUNNER_ALLOW_RUNASROOT=1
CMD ["./run.sh"]
