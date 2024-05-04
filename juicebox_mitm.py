import asyncio
import errno
import logging
import time

import asyncio_dgram
from const import ERROR_LOOKBACK_MIN, MAX_CONNECT_ATTEMPT, MAX_ERROR_COUNT

# https://github.com/rsc-dev/pyproxy MIT
# https://github.com/lucas-six/python-cookbook Apache 2.0
# https://github.com/dannerph/keba-kecontact MIT

_LOGGER = logging.getLogger(__name__)


class JuiceboxMITM:

    def __init__(
        self,
        jpp_addr,
        enelx_addr,
        local_mitm_handler=None,
        ignore_remote=False,
        remote_mitm_handler=None,
        mqtt_handler=None,
        loglevel=None,
    ):
        if loglevel is not None:
            _LOGGER.setLevel(loglevel)
        self._jpp_addr = jpp_addr
        self._enelx_addr = enelx_addr
        self._juicebox_addr = None
        self._ignore_remote = ignore_remote
        self._local_mitm_handler = local_mitm_handler
        self._remote_mitm_handler = remote_mitm_handler
        self._mqtt_handler = mqtt_handler
        self._loop = asyncio.get_running_loop()
        self._mitm_loop_task: asyncio.Task = None
        self._sending_lock = asyncio.Lock()
        self._dgram = None
        self._error_count = 0
        self._error_timestamp_list = []

    async def start(self) -> None:
        _LOGGER.info("Starting JuiceboxMITM")
        _LOGGER.debug(f"JPP: {self._jpp_addr[0]}:{self._jpp_addr[1]}")
        _LOGGER.debug(f"EnelX: {self._enelx_addr[0]}:{self._enelx_addr[1]}")

        await self._connect()

    async def close(self):
        if self._dgram is not None:
            self._dgram.close()
            self._dgram = None
            await asyncio.sleep(3)

    async def _connect(self):
        connect_attempt = 1
        while (
            self._dgram is None
            and connect_attempt <= MAX_CONNECT_ATTEMPT
            and self._error_count < MAX_ERROR_COUNT
        ):
            _LOGGER.debug(
                f"UDP Server Startup attempt {connect_attempt} of {MAX_CONNECT_ATTEMPT}"
            )
            connect_attempt += 1
            try:
                if self._sending_lock.locked():
                    self._dgram = await asyncio_dgram.bind(self._jpp_addr)
                else:
                    async with self._sending_lock:
                        self._dgram = await asyncio_dgram.bind(self._jpp_addr)
            except OSError as e:
                await self._add_error()
                _LOGGER.warning(
                    "JuiceboxMITM UDP Server Startup Error. Reconnecting. "
                    f"({e.__class__.__qualname__}: {e})"
                )
                self._dgram = None
                pass
            await asyncio.sleep(5)
        if self._dgram is None:
            raise ChildProcessError("JuiceboxMITM: Unable to start UDP Server.")
        if self._mitm_loop_task is None or self._mitm_loop_task.done():
            self._mitm_loop_task = await self._mitm_loop()
            self._loop.create_task(self._mitm_loop_task)
        _LOGGER.debug(f"JuiceboxMITM Connected. {self._jpp_addr}")

    async def _mitm_loop(self) -> None:
        _LOGGER.debug("Starting JuiceboxMITM Loop")
        while self._error_count < MAX_ERROR_COUNT:
            if self._dgram is None:
                _LOGGER.warning("JuiceboxMITM Connection Lost. Reconnecting.")
                await self._connect()
                continue
            # _LOGGER.debug("Listening")
            try:
                data, remote_addr = await self._dgram.recv()
            except asyncio_dgram.TransportClosed:
                await self._add_error()
                _LOGGER.warning("JuiceboxMITM Connection Lost. Reconnecting.")
                self._dgram = None
                await self._connect()
                continue
            self._loop.create_task(self._main_mitm_handler(data, remote_addr))
        raise ChildProcessError(
            f"JuiceboxMITM: More than {self._error_count} errors in the last {
                ERROR_LOOKBACK_MIN} min."
        )

    async def _main_mitm_handler(self, data: bytes, from_addr: tuple[str, int]):
        if data is None or from_addr is None:
            return

        # _LOGGER.debug(f"JuiceboxMITM Recv: {data} from {from_addr}")
        if from_addr[0] != self._enelx_addr[0]:
            self._juicebox_addr = from_addr

        if from_addr == self._juicebox_addr:
            data = await self._local_mitm_handler(data)
            if not self._ignore_remote:
                try:
                    await self.send_data(data, self._enelx_addr)
                except OSError as e:
                    await self._add_error()
                    _LOGGER.warning(
                        f"JuiceboxMITM OSError {
                            errno.errorcode[e.errno]} [{self._enelx_addr}]: {e}"
                    )
                    await self._local_mitm_handler(
                        f"JuiceboxMITM_OSERROR|server|{self._enelx_addr}|{
                            errno.errorcode[e.errno]}|{e}"
                    )
        elif self._juicebox_addr is not None and from_addr == self._enelx_addr:
            if not self._ignore_remote:
                data = await self._remote_mitm_handler(data)
                try:
                    await self.send_data(data, self._juicebox_addr)
                except OSError as e:
                    await self._add_error()
                    _LOGGER.warning(
                        f"JuiceboxMITM OSError {
                            errno.errorcode[e.errno]} [{self._juicebox_addr}]: {e}"
                    )
                    await self._local_mitm_handler(
                        f"JuiceboxMITM_OSERROR|client|{self._juicebox_addr}|{
                            errno.errorcode[e.errno]}|{e}"
                    )
            else:
                _LOGGER.info(f"JuiceboxMITM Ignoring Remote: {data}")
        else:
            _LOGGER.warning(f"JuiceboxMITM Unknown address: {from_addr}")

    async def send_data(
        self, data: bytes, to_addr: tuple[str, int], blocking_time: int = 0.1
    ):
        if self._dgram is None:
            _LOGGER.warning("JuiceboxMITM Connection Lost. Reconnecting.")
            await self._connect()
            _LOGGER.warning(f"JuiceboxMITM Resending: {data} to {to_addr}")
            self._loop.create_task(self.send_data(data, to_addr, blocking_time))
            return

        async with self._sending_lock:
            try:
                await self._dgram.send(data, to_addr)
            except asyncio_dgram.TransportClosed:
                await self._add_error()
                _LOGGER.warning("JuiceboxMITM Connection Lost. Reconnecting.")
                self._dgram = None
                await self._connect()
                _LOGGER.warning(f"JuiceboxMITM Resending: {data} to {to_addr}")
                self._loop.create_task(self.send_data(data, to_addr, blocking_time))
                return
            await asyncio.sleep(max(blocking_time, 0.1))

        # _LOGGER.debug(f"JuiceboxMITM Sent: {data} to {to_addr}")

    async def send_data_to_juicebox(self, data: bytes):
        await self.send_data(data, self._juicebox_addr)

    async def set_mqtt_handler(self, mqtt_handler):
        self._mqtt_handler = mqtt_handler

    async def set_local_mitm_handler(self, local_mitm_handler):
        self._local_mitm_handler = local_mitm_handler

    async def set_remote_mitm_handler(self, remote_mitm_handler):
        self._remote_mitm_handler = remote_mitm_handler

    async def _add_error(self):
        self._error_timestamp_list.append(time.time())
        time_cutoff = time.time() - (ERROR_LOOKBACK_MIN * 60)
        temp_list = list(
            filter(lambda el: el > time_cutoff, self._error_timestamp_list)
        )
        self._error_timestamp_list = temp_list
        self._error_count = len(self._error_timestamp_list)
        _LOGGER.debug(f"Errors in last {ERROR_LOOKBACK_MIN} min: {self._error_count}")
