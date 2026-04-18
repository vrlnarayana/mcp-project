from typing import Optional
import database


def register_tools(mcp) -> None:
    @mcp.tool()
    def list_jobs(
        page: int = 1,
        page_size: int = 10,
        location: Optional[str] = None,
        job_type: Optional[str] = None,
        experience_level: Optional[str] = None,
    ) -> dict:
        """List open jobs with optional filters. Returns paginated results with total count.
        job_type values: full-time, contract, remote.
        experience_level values: junior, mid, senior."""
        return database.db_list_jobs(page, page_size, location, job_type, experience_level)

    @mcp.tool()
    def get_job(job_id: int) -> dict:
        """Get a single job record by its numeric ID. Returns all fields including description."""
        return database.db_get_job(job_id)

    @mcp.tool()
    def search_jobs(
        query: str,
        location: Optional[str] = None,
        skill: Optional[str] = None,
    ) -> list:
        """Search open jobs by keyword across title, skills, and description (max 20 results).
        Optionally filter by location (city name) or skill (e.g. 'React', 'Python')."""
        return database.db_search_jobs(query, location, skill)
