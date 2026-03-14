from flask import jsonify


class Result:
    """统一响应格式"""

    def __init__(self, success: bool, data=None, message: str = ""):
        self.success = success
        self.data    = data
        self.message = message

    @classmethod
    def ok(cls, data=None, message: str = "success") -> "Result":
        return cls(True, data, message)

    @classmethod
    def fail(cls, message: str = "error", data=None) -> "Result":
        return cls(False, data, message)

    def to_response(self, status_code: int = None):
        payload = {"success": self.success, "message": self.message}
        if self.data is not None:
            payload["data"] = self.data
        code = status_code or (200 if self.success else 400)
        return jsonify(payload), code