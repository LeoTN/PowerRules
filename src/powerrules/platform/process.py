import psutil


# psutil already makes everything platform independent
class PsUtilProcessProvider:
    """Provide process information on Windows, Linux and macOS."""

    def get_process_names(self) -> tuple[str, ...]:
        """Return a list of all currently existing process names.

        Returns:
            A tuple of process names.
        """
        return tuple(process.info["name"] for process in psutil.process_iter(["name"]))
