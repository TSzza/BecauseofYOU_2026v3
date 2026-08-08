"""NLP-only novel indexing pipeline for Because of YOU."""

__all__ = ["NovelIndexer", "index_novel"]


def __getattr__(name: str):
    if name in __all__:
        from .pipeline import NovelIndexer, index_novel
        return {"NovelIndexer": NovelIndexer, "index_novel": index_novel}[name]
    raise AttributeError(name)
