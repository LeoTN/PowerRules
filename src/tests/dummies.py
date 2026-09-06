# Contains dummy objects used by tests

from datetime import datetime

from pydantic import BaseModel

##################
# Condtion objects
##################


# This condition keeps track of its evaluation count and returns its predetermined evaluation result. If an exception is given, it will be raised
class Dummy_Condition:
    def __init__(self, given_result: bool, given_exception: Exception | None = None):
        self.given_result = given_result
        self.given_exception = given_exception
        self.evaluation_count = 0

    def evaluate(self) -> bool:
        self.evaluation_count += 1

        if self.given_exception is not None:
            raise self.given_exception

        return self.given_result


# This action keeps track of its execution count. If an exception is given, it will be raised
class Dummy_Action:
    def __init__(self, given_exception: Exception | None = None):
        self.given_exception = given_exception
        self.execution_count = 0

    def execute(self) -> None:
        self.execution_count += 1

        if self.given_exception is not None:
            raise self.given_exception


##################
# Provider objects
##################


# Dummy clock provider which returns its predetermined time
class Dummy_ClockProvider:
    def __init__(self, given_time: datetime):
        self.given_time = given_time

    def now(self) -> datetime:
        return self.given_time


# Keep track of the number of times each action is executed. Raises an exception if the given exception is not None
class Dummy_PowerProvider:
    def __init__(self, given_exception: Exception | None = None):
        self.given_exception = given_exception
        self.shutdown_count = 0
        self.sleep_count = 0
        self.hibernate_count = 0
        self.reboot_count = 0

    def shutdown(self) -> None:
        self.shutdown_count += 1

        if self.given_exception is not None:
            raise self.given_exception

    def sleep(self) -> None:
        self.sleep_count += 1

        if self.given_exception is not None:
            raise self.given_exception

    def hibernate(self) -> None:
        self.hibernate_count += 1

        if self.given_exception is not None:
            raise self.given_exception

    def reboot(self) -> None:
        self.reboot_count += 1

        if self.given_exception is not None:
            raise self.given_exception


#####################
# Other dummy objects
#####################


class Dummy_Process:
    def __init__(self, process_name: str | None):
        self.info = {
            "name": process_name,
        }


# Dummy exception used to terminate the continously running evaluation loop
class Dummy_StopEvaluation(Exception):
    pass


# Dummy model used to call the validation function
class Dummy_Model(BaseModel):
    enabled: bool
