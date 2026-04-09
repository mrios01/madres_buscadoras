from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


StatusType = Literal["ACTIVE_SEARCH", "FOUND_ALIVE", "FOUND_DECEASED"]
RoleType = Literal["SEARCHER", "BRIGADE_LEADER", "ADMIN"]
VerificationType = Literal["PENDING", "VERIFIED", "REVOKED"]


class LocationLastSeen(BaseModel):
    city: str = Field(min_length=1, max_length=120)
    state: str = Field(min_length=1, max_length=120)
    neighborhood: str = Field(min_length=1, max_length=160)


class PhysicalDescription(BaseModel):
    height_cm: int | None = Field(default=None, ge=30, le=260)
    weight_kg: int | None = Field(default=None, ge=2, le=350)
    identifying_marks: list[str] = Field(default_factory=list, max_length=15)
    clothing_last_seen: str = Field(min_length=1, max_length=300)


class PublicFicha(BaseModel):
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=200)
    age_at_disappearance: int = Field(ge=0, le=120)
    gender: str = Field(min_length=1, max_length=20)
    date_missing: datetime
    location_last_seen: LocationLastSeen
    physical_description: PhysicalDescription
    primary_image_url: str = Field(min_length=4, max_length=1024)


class PrivateDossierCreate(BaseModel):
    authorized_collective_ids: list[str] = Field(default_factory=list)
    official_case_number: str = Field(min_length=1, max_length=120)
    dna_sample_registered: bool = False
    suspected_context: str = Field(min_length=1, max_length=2000)
    internal_notes: str = Field(min_length=1, max_length=5000)


class MissingPersonCreate(BaseModel):
    status: StatusType = "ACTIVE_SEARCH"
    public_ficha: PublicFicha
    private_dossier: PrivateDossierCreate
