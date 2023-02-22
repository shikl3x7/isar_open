FROM ghcr.io/siemens/kas/kas-isar:latest

ARG TARGETPLATFORM
ARG DEBIAN_FRONTEND=noninteractive

USER root

# Isar testsuite dependencies
RUN pip3 --proxy=$https_proxy install avocado-framework==100.1 && \
    rm -rf $(pip3 cache dir) && \
    apt-get update && \
    apt-get install -y -f --no-install-recommends \
        qemu-system ovmf

RUN apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* 

USER builder
