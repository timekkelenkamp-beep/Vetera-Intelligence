from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Document, PremiumObservation, Product, ProductVersion, Provider, RiskCarrier
from ..services.analysis import product_label, product_summary
from ..services.common import VEHICLE_CATEGORIES, apply_updates, audit, get_or_404, to_dict

router = APIRouter(prefix="/api", tags=["producten"])
FIELDS = ["name", "vehicle_category", "description", "url", "status", "notes", "risk_carrier_id",
          "canonical_product_id", "provider_id"]


def _check_canonical(db: Session, p: Product, canonical_id):
    if canonical_id in (None, ""):
        return
    c = db.get(Product, int(canonical_id))
    if not c or c.id == p.id or c.canonical_product_id:
        raise HTTPException(422, "Ongeldig canoniek product (moet een ander, zelfstandig product zijn)")


@router.get("/products")
def list_products(provider_id: int | None = None, vehicle_category: str | None = None,
                  include_distribution: bool = True, db: Session = Depends(get_db)):
    stmt = select(Product).join(Provider, Product.provider_id == Provider.id).where(Provider.status != "samengevoegd")
    if provider_id:
        stmt = stmt.where(Product.provider_id == provider_id)
    if vehicle_category:
        stmt = stmt.where(Product.vehicle_category.in_([vehicle_category, "meerdere"]))
    if not include_distribution:
        stmt = stmt.where(Product.canonical_product_id.is_(None))
    out = []
    for p in db.scalars(stmt):
        d = to_dict(p)
        d.update({k: v for k, v in product_label(db, p).items() if k not in d})
        d["provider_status"] = db.get(Provider, p.provider_id).status
        out.append(d)
    out.sort(key=lambda r: (not r["is_reference"], r["provider_name"].lower(), r["name"].lower()))
    return out


@router.post("/products")
def create_product(data: dict, db: Session = Depends(get_db)):
    if not data.get("provider_id") or not (data.get("name") or "").strip():
        raise HTTPException(422, "Aanbieder en productnaam zijn verplicht")
    get_or_404(db, Provider, int(data["provider_id"]), "Aanbieder")
    p = Product(provider_id=int(data["provider_id"]), name=data["name"].strip())
    db.add(p)
    db.flush()
    _check_canonical(db, p, data.get("canonical_product_id"))
    apply_updates(db, p, data, FIELDS, "product", enums={"vehicle_category": VEHICLE_CATEGORIES})
    audit(db, "product", p.id, "aangemaakt", {"name": p.name})
    db.commit()
    return to_dict(p)


@router.get("/products/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db)):
    p = get_or_404(db, Product, product_id, "Product")
    vetera = db.scalars(select(Product).join(Provider, Product.provider_id == Provider.id)
                        .where(Provider.is_reference.is_(True))).first()
    d = to_dict(p)
    d["summary"] = product_summary(db, p, vetera)
    d["versions"] = [to_dict(v) for v in db.scalars(select(ProductVersion).where(ProductVersion.product_id == p.id))]
    d["documents"] = [to_dict(x) for x in db.scalars(select(Document).where(Document.product_id == p.id))]
    d["distributions"] = [product_label(db, x) for x in db.scalars(select(Product).where(Product.canonical_product_id == p.id))]
    d["canonical"] = product_label(db, db.get(Product, p.canonical_product_id)) if p.canonical_product_id else None
    d["risk_carrier"] = to_dict(p.risk_carrier) if p.risk_carrier else None
    d["premium_count"] = len(db.scalars(select(PremiumObservation.id).where(PremiumObservation.product_id == p.id)).all())
    return d


@router.patch("/products/{product_id}")
def update_product(product_id: int, data: dict, db: Session = Depends(get_db)):
    p = get_or_404(db, Product, product_id, "Product")
    if "canonical_product_id" in data:
        _check_canonical(db, p, data["canonical_product_id"])
    apply_updates(db, p, data, FIELDS, "product", enums={"vehicle_category": VEHICLE_CATEGORIES})
    db.commit()
    return to_dict(p)


@router.delete("/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    p = get_or_404(db, Product, product_id, "Product")
    audit(db, "product", p.id, "verwijderd", {"name": p.name})
    for x in db.scalars(select(Product).where(Product.canonical_product_id == p.id)):
        x.canonical_product_id = None
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.post("/products/{product_id}/versions")
def add_version(product_id: int, data: dict, db: Session = Depends(get_db)):
    get_or_404(db, Product, product_id, "Product")
    v = ProductVersion(product_id=product_id, label=data.get("label") or "Versie")
    db.add(v)
    db.flush()
    apply_updates(db, v, data, ["label", "valid_from", "valid_to", "notes"], "product_version",
                  date_fields=["valid_from", "valid_to"])
    db.commit()
    return to_dict(v)


@router.get("/risk-carriers")
def list_carriers(db: Session = Depends(get_db)):
    return [to_dict(r) for r in db.scalars(select(RiskCarrier).order_by(RiskCarrier.name))]


@router.post("/risk-carriers")
def create_carrier(data: dict, db: Session = Depends(get_db)):
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(422, "Naam is verplicht")
    if db.scalars(select(RiskCarrier).where(RiskCarrier.name == name)).first():
        raise HTTPException(409, "Risicodrager bestaat al")
    r = RiskCarrier(name=name, website=data.get("website"), notes=data.get("notes"))
    db.add(r)
    db.commit()
    return to_dict(r)
