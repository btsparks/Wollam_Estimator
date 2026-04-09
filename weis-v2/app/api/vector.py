"""Vector search API endpoints — semantic search across bid documents and institutional memory."""

from fastapi import APIRouter, HTTPException, Query

from app.config import VECTOR_SEARCH_ENABLED

router = APIRouter(prefix="/api/search", tags=["search"])


def _check_enabled():
    if not VECTOR_SEARCH_ENABLED:
        raise HTTPException(status_code=400, detail="Vector search is disabled")


@router.get("/bids/{bid_id}")
async def search_bid_documents(
    bid_id: int,
    q: str = Query(..., min_length=1),
    n: int = Query(10, ge=1, le=50),
    category: str | None = Query(None),
):
    """Semantic search within a bid's documents."""
    _check_enabled()
    from app.services.vector_store import search_bid
    results = search_bid(bid_id, q, n_results=n, doc_category=category)
    return {"bid_id": bid_id, "query": q, "results": results, "count": len(results)}


@router.get("/historical")
async def search_historical(
    q: str = Query(..., min_length=1),
    n: int = Query(10, ge=1, le=50),
):
    """Semantic search across institutional memory."""
    _check_enabled()
    from app.services.vector_store import search_institutional
    results = search_institutional(q, n_results=n)
    return {"query": q, "results": results, "count": len(results)}


@router.get("/index-stats")
async def index_stats(bid_id: int | None = Query(None)):
    """Return embedding counts per collection."""
    _check_enabled()
    from app.services.vector_store import get_index_stats
    return get_index_stats(bid_id)


@router.post("/bids/{bid_id}/rebuild")
async def rebuild_bid(bid_id: int):
    """Rebuild a single bid's vector index from SQLite."""
    _check_enabled()
    from app.services.vector_store import rebuild_bid_index
    result = rebuild_bid_index(bid_id)
    return {"bid_id": bid_id, **result}


@router.post("/rebuild")
async def rebuild_all():
    """Rebuild all bid indexes plus institutional memory."""
    _check_enabled()
    from app.services.vector_store import rebuild_bid_index, rebuild_institutional_index, get_index_stats
    from app.database import get_connection

    conn = get_connection()
    try:
        bids = conn.execute("SELECT id FROM active_bids").fetchall()
    finally:
        conn.close()

    results = {}
    for bid in bids:
        results[bid["id"]] = rebuild_bid_index(bid["id"])

    institutional = rebuild_institutional_index()
    return {
        "bids": results,
        "institutional": institutional,
        "stats": get_index_stats(),
    }
