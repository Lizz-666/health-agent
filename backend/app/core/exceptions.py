class AppException(Exception):
    def __init__(self, status_code: int, detail: str, code: str = "error"):
        self.status_code = status_code
        self.detail = detail
        self.code = code


class Unauthorized(AppException):
    def __init__(self, detail: str = "未登录或登录已过期"):
        super().__init__(401, detail, "unauthorized")


class Forbidden(AppException):
    def __init__(self, detail: str = "无权限"):
        super().__init__(403, detail, "forbidden")


class NotFound(AppException):
    def __init__(self, detail: str = "资源不存在"):
        super().__init__(404, detail, "not_found")


class BadRequest(AppException):
    def __init__(self, detail: str = "请求参数错误"):
        super().__init__(400, detail, "bad_request")
