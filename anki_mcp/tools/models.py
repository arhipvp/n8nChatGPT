"""Инструменты Anki, связанные с моделями."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Union

from .. import app, config
from ..compat import model_validate
from ..schemas import (
    CardTemplateSpec,
    CreateModelArgs,
    CreateModelResult,
    ListModelsResponse,
    ModelInfo,
    ModelSummary,
    UpdateModelStylingArgs,
    UpdateModelTemplatesArgs,
)
from ..services import anki as anki_services
from ..services import client as anki_client


def _normalize_template(template: CardTemplateSpec) -> Dict[str, str]:
    return {
        "Name": template.name,
        "Front": template.front,
        "Back": template.back,
    }


@app.tool(name="anki.create_model")
async def create_model(
    args: Union[CreateModelArgs, Mapping[str, Any]]
) -> CreateModelResult:
    if isinstance(args, CreateModelArgs):
        normalized = args
    else:
        try:
            normalized = model_validate(CreateModelArgs, args)
        except Exception as exc:
            raise ValueError(f"Invalid create_model arguments: {exc}") from exc

    reserved = {"modelName", "inOrderFields", "cardTemplates", "css"}
    extra_options = dict(normalized.options)
    for key in extra_options:
        if key in reserved:
            raise ValueError(
                f"options cannot override reserved parameter {key!r}"
            )

    payload = {
        "modelName": normalized.model_name,
        "inOrderFields": normalized.in_order_fields,
        "cardTemplates": [
            _normalize_template(template) for template in normalized.card_templates
        ],
        "css": normalized.css,
    }

    if normalized.is_cloze is not None:
        existing = extra_options.get("isCloze")
        if existing is not None and existing != normalized.is_cloze:
            raise ValueError(
                "is_cloze conflicts with options['isCloze'] value"
            )
        payload["isCloze"] = normalized.is_cloze
        extra_options["isCloze"] = normalized.is_cloze

    payload.update(extra_options)

    anki_response = await anki_client.anki_call("createModel", payload)

    return CreateModelResult(
        model_name=normalized.model_name,
        in_order_fields=normalized.in_order_fields,
        card_templates=list(normalized.card_templates),
        css=normalized.css,
        options=extra_options,
        anki_response=anki_response,
    )


@app.tool(name="anki.update_model_templates")
async def update_model_templates(
    args: Union[UpdateModelTemplatesArgs, Mapping[str, Any]]
) -> Any:
    if isinstance(args, UpdateModelTemplatesArgs):
        normalized = args
    else:
        try:
            normalized = model_validate(UpdateModelTemplatesArgs, args)
        except Exception as exc:
            raise ValueError(
                f"Invalid update_model_templates arguments: {exc}"
            ) from exc

    templates_payload: Dict[str, Dict[str, str]] = {}
    for key, template in normalized.templates.items():
        template_name = template.name
        if not template_name:
            raise ValueError("Template name must be a non-empty string")
        key_stripped = key.strip()
        if key_stripped and key_stripped != template_name:
            raise ValueError(
                f"Template mapping key {key!r} must match template name {template_name!r}"
            )
        if template_name in templates_payload:
            raise ValueError(f"Duplicate template definition for {template_name!r}")
        templates_payload[template_name] = {
            "Front": template.front,
            "Back": template.back,
        }

    payload = {
        "model": {
            "name": normalized.model_name,
            "templates": templates_payload,
        }
    }

    return await anki_client.anki_call("updateModelTemplates", payload)


@app.tool(name="anki.update_model_styling")
async def update_model_styling(
    args: Union[UpdateModelStylingArgs, Mapping[str, Any]]
) -> Any:
    if isinstance(args, UpdateModelStylingArgs):
        normalized = args
    else:
        try:
            normalized = model_validate(UpdateModelStylingArgs, args)
        except Exception as exc:
            raise ValueError(
                f"Invalid update_model_styling arguments: {exc}"
            ) from exc

    payload = {
        "model": {
            "name": normalized.model_name,
            "styling": {"css": normalized.css},
        }
    }

    return await anki_client.anki_call("updateModelStyling", payload)


@app.tool(name="anki.list_models")
async def list_models() -> ListModelsResponse:
    raw_models = await anki_client.anki_call("modelNamesAndIds", {})

    if raw_models is None:
        return ListModelsResponse()

    if not isinstance(raw_models, Mapping):
        raise ValueError(
            "modelNamesAndIds response must be a mapping of model names to ids"
        )

    model_summaries: List[ModelSummary] = []
    for name, model_id in raw_models.items():
        if not isinstance(name, str):
            raise ValueError(
                f"modelNamesAndIds returned invalid model name: {name!r}"
            )

        if isinstance(model_id, bool):
            raise ValueError(
                "modelNamesAndIds returned non-integer model id "
                f"for {name!r}: {model_id!r}"
            )

        try:
            normalized_id = int(model_id)
        except (TypeError, ValueError):
            raise ValueError(
                "modelNamesAndIds returned non-integer model id "
                f"for {name!r}: {model_id!r}"
            ) from None

        model_summaries.append(ModelSummary(id=normalized_id, name=name))

    sorted_models = sorted(
        model_summaries, key=lambda model: (model.name.casefold(), model.name)
    )

    return ListModelsResponse(models=sorted_models)


@app.tool(name="anki.model_info")
async def model_info(model: Optional[str] = None) -> ModelInfo:
    target_model = model or config.DEFAULT_MODEL
    fields, templates, css = await anki_services.get_model_fields_templates(target_model)
    return ModelInfo(model=target_model, fields=fields, templates=templates, styling=css)


__all__ = [
    "create_model",
    "update_model_templates",
    "update_model_styling",
    "list_models",
    "model_info",
]
