"""
Discipline Mapper — Cost Code to Discipline Mapping

Maps Wollam's HCSS cost codes to construction disciplines using
configurable rules from config/discipline_map.yaml.

Wollam uses 4-digit cost codes where the first 2 digits generally
indicate the discipline (e.g., 22xx = Concrete, 24xx = Structural Steel).
But there are exceptions — specific codes that belong to a different
discipline than their prefix suggests. The mapper handles these via
a priority system:

    1. Exact override (highest priority) — config.overrides dict
    2. Specific codes — discipline.specific_codes list
    3. Subcategory codes — discipline.subcategories dict
    4. Prefix match — discipline.code_prefixes list (2-digit prefix)
    5. "unmapped" (lowest) — flagged for manual review
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


# Default config path — relative to project root
DEFAULT_CONFIG_PATH = os.path.join("config", "discipline_map.yaml")


class DisciplineMapper:
    """
    Maps cost codes to disciplines using configurable rules.

    Loads mapping rules from a YAML config file. The config defines
    disciplines with code prefixes, specific codes, subcategories,
    and manual overrides.

    Usage:
        mapper = DisciplineMapper()
        discipline = mapper.map_code("2215")       # → 'concrete'
        discipline = mapper.map_code("5100")       # → 'ss_pipe_conveyance' (override)
        discipline = mapper.map_code("9999")       # → 'unmapped'
        subcat = mapper.get_subcategory("2215")    # → 'forming'
    """

    def __init__(self, config_path: str | None = None):
        """
        Load discipline mapping rules from YAML config.

        Args:
            config_path: Path to discipline_map.yaml.
                         Defaults to config/discipline_map.yaml.
        """
        config_path = config_path or DEFAULT_CONFIG_PATH

        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        self._disciplines: dict[str, dict[str, Any]] = config.get("disciplines", {})
        self._overrides: dict[str, str] = config.get("overrides", {})

        # Build lookup indexes for fast mapping
        self._prefix_index: dict[str, str] = {}       # "22" → "concrete"
        self._specific_index: dict[str, str] = {}      # "2405" → "ss_pipe_conveyance"
        self._subcategory_index: dict[str, str] = {}   # "2215" → "forming"
        self._subcat_to_discipline: dict[str, str] = {}  # "2215" → "concrete"

        self._build_indexes()

    def _build_indexes(self) -> None:
        """Pre-compute lookup indexes from the config for O(1) mapping."""
        for disc_key, disc_config in self._disciplines.items():
            # Index code prefixes (2-digit)
            for prefix in disc_config.get("code_prefixes", []):
                self._prefix_index[prefix] = disc_key

            # Also index material_prefixes and sub_prefixes as belonging to this discipline
            for prefix in disc_config.get("material_prefixes", []):
                self._prefix_index[prefix] = disc_key
            for prefix in disc_config.get("sub_prefixes", []):
                self._prefix_index[prefix] = disc_key

            # Index specific codes (exact match)
            for code in disc_config.get("specific_codes", []):
                self._specific_index[code] = disc_key

            # Index subcategory codes
            for subcat_name, codes in disc_config.get("subcategories", {}).items():
                for code in codes:
                    self._subcategory_index[code] = subcat_name
                    self._subcat_to_discipline[code] = disc_key

    def map_code(self, cost_code: str, description: str | None = None) -> str:
        """
        Map a cost code to its discipline.

        Priority order:
            1. Exact override (manual exceptions)
            2. Specific codes (discipline-level exact match)
            3. Subcategory codes (subcategory-level exact match)
            4. 2-digit prefix match
            5. "unmapped" (needs manual review)

        Args:
            cost_code: 4-digit cost code string (e.g., '2215').
            description: Optional description for future AI-assisted mapping.

        Returns:
            Discipline key (e.g., 'concrete', 'earthwork', 'unmapped').
        """
        code = str(cost_code).strip()

        # 1. Check overrides (highest priority — manual exceptions)
        if code in self._overrides:
            return self._overrides[code]

        # 2. Check specific codes (e.g., SS pipe conveyance codes)
        if code in self._specific_index:
            return self._specific_index[code]

        # 3. Check subcategory codes (implies discipline)
        if code in self._subcat_to_discipline:
            return self._subcat_to_discipline[code]

        # 4. Match by 2-digit prefix
        if len(code) >= 2:
            prefix = code[:2]
            if prefix in self._prefix_index:
                return self._prefix_index[prefix]

        # 5. No match — flag for manual review
        return "unmapped"

    def get_subcategory(self, cost_code: str) -> str | None:
        """
        Get the subcategory for a cost code, if one is defined.

        Args:
            cost_code: 4-digit cost code string.

        Returns:
            Subcategory name (e.g., 'forming', 'rebar') or None.
        """
        return self._subcategory_index.get(str(cost_code).strip())

    def get_all_codes_for_discipline(self, discipline: str) -> list[str]:
        """
        Get all known cost codes that map to a discipline.

        Includes codes from overrides, specific_codes, and subcategories.
        Does NOT include all possible prefix matches (those are unbounded).

        Args:
            discipline: Discipline key (e.g., 'concrete').

        Returns:
            List of known cost code strings.
        """
        codes: list[str] = []

        # From overrides
        for code, disc in self._overrides.items():
            if disc == discipline:
                codes.append(code)

        # From specific codes
        for code, disc in self._specific_index.items():
            if disc == discipline:
                codes.append(code)

        # From subcategories
        for code, disc in self._subcat_to_discipline.items():
            if disc == discipline:
                codes.append(code)

        return sorted(set(codes))

    def get_discipline_name(self, discipline_key: str) -> str:
        """
        Get the display name for a discipline key.

        Args:
            discipline_key: Internal key (e.g., 'concrete').

        Returns:
            Display name (e.g., 'Concrete') or the key itself if not found.
        """
        disc = self._disciplines.get(discipline_key, {})
        return disc.get("name", discipline_key)

    @property
    def all_disciplines(self) -> list[str]:
        """List all configured discipline keys."""
        return list(self._disciplines.keys())
