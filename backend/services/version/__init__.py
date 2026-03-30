from database.repository.version import VersionRepository
from result import Result


class VersionService:

    @staticmethod
    def get_latest() -> Result:
        v = VersionRepository.get_latest()
        if not v:
            return Result.fail("暂无版本信息")
        return Result.ok(data={
            "id":           v.id,
            "version":      v.version,
            "description":  v.description,
            "download_url": v.download_url,
            "releaseDate":  v.created_at.strftime("%Y-%m-%d"),
        })

    @staticmethod
    def create(version: str, description: str,
               download_url: str = None, mac_download_url: str = None) -> Result:
        v = VersionRepository.create(version, description, download_url, mac_download_url)
        return Result.ok(data={"id": v.id, "version": v.version})


version_service = VersionService()
