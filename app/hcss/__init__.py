"""
HCSS API Integration Module

Connects to HeavyJob (field cost tracking) and HeavyBid (estimating)
through their published APIs. Handles authentication, pagination,
rate limiting, and response deserialization.

Submodules:
    auth      - OAuth 2.0 token management
    client    - Base HTTP client with retry and pagination
    heavyjob  - HeavyJob API endpoint wrappers
    heavybid  - HeavyBid API endpoint wrappers
    models    - Pydantic response models for all API data
    sync      - Sync orchestration (stub until Phase D)
"""
