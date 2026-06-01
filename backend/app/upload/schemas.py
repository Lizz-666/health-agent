from pydantic import BaseModel


class STSTokenResponse(BaseModel):
    access_key_id: str
    access_key_secret: str
    security_token: str
    bucket: str
    region: str
    endpoint: str
    path_prefix: str
