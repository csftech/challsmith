# No ctferio/ctfd tag combines CTFd 3.8.9 with ctfd-chall-manager v0.10.1 (latest bundle is 3.8.6-0.10.1), so bake the plugin in here.
FROM alpine/git:v2.47.2 AS plugin
RUN git clone --depth 1 --branch v0.10.1 https://github.com/ctfer-io/ctfd-chall-manager /plugin

FROM ctfd/ctfd:3.8.9
COPY --from=plugin --chown=ctfd:ctfd /plugin /opt/CTFd/CTFd/plugins/ctfd_chall_manager
RUN if [ -f /opt/CTFd/CTFd/plugins/ctfd_chall_manager/requirements.txt ]; then \
      pip install --no-cache-dir -r /opt/CTFd/CTFd/plugins/ctfd_chall_manager/requirements.txt; fi
