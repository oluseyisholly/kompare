from sqlalchemy.orm import Session

from app.models.provider import Provider


class ProviderRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_slug(self, slug: str) -> Provider | None:
        return self.db.query(Provider).filter(Provider.slug == slug).first()

    def list_all(self) -> list[Provider]:
        return self.db.query(Provider).order_by(Provider.name.asc(), Provider.id.asc()).all()

    def create(self, provider: Provider) -> Provider:
        self.db.add(provider)
        self.db.commit()
        self.db.refresh(provider)
        return provider

    def update(self, provider: Provider, **fields) -> Provider:
        for key, value in fields.items():
            setattr(provider, key, value)

        self.db.commit()
        self.db.refresh(provider)
        return provider

    def get_or_create_by_slug(
        self,
        *,
        slug: str,
        name: str,
        category,
        description: str | None = None,
        logo_url: str | None = None,
        website_url: str | None = None,
        has_adapter: bool = False,
        metadata_json: dict | None = None,
    ) -> Provider:
        provider = self.get_by_slug(slug)
        if provider is not None:
            return provider

        provider = Provider(
            slug=slug,
            name=name,
            description=description,
            logo_url=logo_url,
            website_url=website_url,
            category=category,
            has_adapter=has_adapter,
            metadata_json=metadata_json,
        )
        return self.create(provider)
