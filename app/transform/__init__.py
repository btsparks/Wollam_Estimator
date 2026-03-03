"""
Data Transformation Module

Converts raw HCSS API data into calculated rate cards.
Handles cost code mapping, unit cost calculation, confidence
assessment, variance flagging, and rate card assembly.

Submodules:
    mapper     - Cost code to discipline mapping (reads config/discipline_map.yaml)
    calculator - Unit cost calculations ($/unit, MH/unit, recommended rates)
    rate_card  - Rate card generation and assembly
    validator  - Data validation and outlier detection
"""
