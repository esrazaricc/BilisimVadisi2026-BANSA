# CHATBOT_RAG_GENERATOR_V1_4

from __future__ import annotations

from dataclasses import dataclass
import gc
import re
import time
import unicodedata


MODEL_ID_DEFAULT = (
    "Qwen/Qwen3-0.6B"
)


_ALLOWED_ROUTES = {
    "campaign_rag",
    "product_rag",
}


@dataclass(frozen=True)
class RagGeneratedAnswer:

    text: str

    raw_model_text: str
    sanitized_model_text: str

    passed_guard: bool

    cited_evidence_ids: tuple[str, ...]
    allowed_evidence_ids: tuple[str, ...]

    guard_reasons: tuple[str, ...]
    guard_warnings: tuple[str, ...]

    model_id: str

    input_tokens: int
    generated_tokens: int

    generation_seconds: float
    tokens_per_second: float


def _guard_normalize(
    value,
) -> str:

    text = unicodedata.normalize(
        "NFKD",
        str(
            value
            or ""
        ),
    )

    text = "".join(
        char
        for char in text
        if not unicodedata.combining(
            char
        )
    )

    return (
        text
        .casefold()
        .strip()
    )


def _numeric_tokens(
    text: str,
) -> set[str]:

    raw = re.findall(
        r"\d+(?:[.,]\d+)*",
        str(
            text
            or ""
        ),
    )

    result = set()

    for value in raw:

        normalized = re.sub(
            r"[^0-9]",
            "",
            value,
        )

        if normalized:

            result.add(
                normalized
            )

    return result


def _group_evidence_by_document(
    context,
):

    groups = {}

    order = []


    for item in context.evidence:

        key = (
            str(
                item.bank_name
            ),
            str(
                item.document_title
            ),
            str(
                item.source_url
            ),
        )


        if key not in groups:

            groups[
                key
            ] = []

            order.append(
                key
            )


        groups[
            key
        ].append(
            item
        )


    return tuple(
        tuple(
            groups[key]
        )
        for key in order
    )


def build_rag_generation_messages(
    context,
    *,
    evidence_group=None,
) -> list[dict[str, str]]:

    if context.route not in (
        _ALLOWED_ROUTES
    ):

        raise ValueError(
            "Local RAG generator is allowed "
            "only for campaign_rag and "
            "product_rag."
        )


    if (
        context.answer_mode
        != "rag"
    ):

        raise ValueError(
            "Grounded context is not "
            "RAG answer mode."
        )


    if not (
        context.may_generate_answer
    ):

        raise ValueError(
            "Grounded Answer Contract "
            "blocked answer generation."
        )


    evidence = tuple(
        evidence_group
        if evidence_group is not None
        else context.evidence
    )


    if not evidence:

        raise ValueError(
            "No selected evidence is "
            "available for generation."
        )


    blocks = []


    for item in evidence:

        text = str(
            item.text
            or ""
        ).strip()

        url = str(
            item.source_url
            or ""
        ).strip()


        if not text:

            raise ValueError(
                "Evidence has empty text."
            )


        if not url:

            raise ValueError(
                "Evidence has no source URL."
            )


        blocks.append(
            (
                "Banka: "
                + str(
                    item.bank_name
                )
                + "\nBelge: "
                + str(
                    item.document_title
                )
                + "\nB\u00f6l\u00fcm: "
                + str(
                    item.section_type
                )
                + "\nKan\u0131t: "
                + text
            )
        )


    evidence_text = (
        "\n\n".join(
            blocks
        )
    )


    system_prompt = (
        "Kullanicinin sorusunu sadece verilen "
        "KANIT metnine dayanarak Turkce yanitla.\n"
        "Dogrudan cevabi yaz; talimatlari tekrar etme.\n"
        "Kanitta olmayan bilgi, tutar, tarih, oran, "
        "sure, limit veya kosul ekleme.\n"
        "Finansal hesaplama veya banka tavsiyesi yapma.\n"
        "URL, kaynak veya citation etiketi yazma.\n"
        "Cevap:, Cevabiniz:, KANIT:, Kaynaklar: gibi "
        "basliklar yazma.\n"
        "Yalniz 1-3 kisa madde yaz.\n"
        "Her madde tam bir cumle ile bitsin.\n"
        "Sorunun cevabi kanitta yoksa sadece "
        "'Bu bilgi verilen kaynakta yer almiyor.' yaz."
    )


    user_prompt = (
        "KULLANICI SORUSU:\n"
        + str(
            context.question
        )
        + "\n\nKANIT:\n"
        + evidence_text
        + "\n\n"
        + "Yalniz bu kanita dayanarak "
        + "1-3 maddelik Turkce cevap ver."
    )


    return [
        {
            "role":
                "system",

            "content":
                system_prompt,
        },
        {
            "role":
                "user",

            "content":
                user_prompt,
        },
    ]


def sanitize_document_answer(
    text: str,
    *,
    evidence_group,
    question: str | None = None,
):

    raw = str(
        text
        or ""
    ).strip()


    if not raw:

        return (
            False,
            "",
            (
                "empty_model_answer",
            ),
            tuple(),
        )


    lowered_raw = (
        raw.casefold()
    )


    if (
        "<think>"
        in lowered_raw
        or "</think>"
        in lowered_raw
    ):

        return (
            False,
            "",
            (
                "thinking_output_present",
            ),
            tuple(),
        )


    evidence_blob = "\n".join(
        str(
            item.text
            or ""
        )
        for item in evidence_group
    )


    allowed_numbers = (
        _numeric_tokens(
            evidence_blob
        )
    )


    banned_advice = (
        "en uygun banka",
        "en iyi banka",
        "en avantajli banka",
        "daha uygun banka",
        "tavsiye ederim",
        "oneriyorum",
        "tercih etmenizi",
    )


    heading_values = {
        "cevap",
        "cevap:",
        "cevab",
        "cevab:",
        "cevabiniz",
        "cevabiniz:",
        "kanit",
        "kanit:",
        "kaynak",
        "kaynak:",
        "kaynaklar",
        "kaynaklar:",
        "kural",
        "kural:",
        "kurallar",
        "kurallar:",
        "kesin kurallar",
        "kesin kurallar:",
        "ornek",
        "ornek:",
    }


    instruction_echo_terms = (
        "yalnizca verilen",
        "yalniz verilen",
        "genel bilgileri kullanma",
        "kendi genel bilgini",
        "eksik bilgi",
        "tahmin",
        "kaynak bulunmayan",
        "finansal hesaplama",
        "url yazma",
        "citation etiketi",
        "kaynak etiketi",
        "dusunme metni",
        "reklam dili",
        "banka tavsiyesi",
        "talimatlari tekrar",
    )


    placeholder_terms = (
        "dogrulanmis ilk bilgi",
        "dogrulanmis ikinci bilgi",
        "dogrulanmis ucuncu bilgi",
    )


    safe_lines = []

    warnings = []


    for number, line in enumerate(
        raw.splitlines(),
        start=1,
    ):

        stripped = (
            line.strip()
        )


        if not stripped:
            continue


        # Small local models sometimes prefix
        # the actual answer with "Cevabiniz:",
        # "Cevab:" or "Cevap:". Preserve the
        # factual content but remove the prefix.

        prefix_normalized = (
            _guard_normalize(
                stripped
            )
        )


        answer_prefixes = (
            "cevabiniz:",
            "cevab:",
            "cevap:",
        )


        if any(
            prefix_normalized.startswith(
                prefix
            )
            for prefix in answer_prefixes
        ):

            colon_index = (
                stripped.find(":")
            )


            if colon_index >= 0:

                stripped = (
                    stripped[
                        colon_index + 1:
                    ]
                    .strip()
                )


                warnings.append(
                    f"stripped_answer_prefix:{number}"
                )


            if not stripped:
                continue


        normalized = (
            _guard_normalize(
                stripped
            )
        )


        normalized_heading = (
            normalized
            .replace(
                "*",
                "",
            )
            .replace(
                "#",
                "",
            )
            .strip()
        )


        # Never expose retrieval metadata as
        # user-facing answer prose.

        metadata_prefixes = (
            "banka:",
            "belge:",
            "bolum:",
            "kanit:",
            "source:",
            "document:",
        )


        if any(
            normalized_heading.startswith(
                prefix
            )
            for prefix in metadata_prefixes
        ):

            warnings.append(
                f"dropped_metadata_line:{number}"
            )

            continue


        # Small models may repeat the user's
        # question verbatim before answering.
        # Remove that echo deterministically.

        if question:

            normalized_question = (
                _guard_normalize(
                    question
                )
                .strip()
            )


            candidate_question = (
                normalized_heading
                .lstrip(
                    "-* "
                )
                .strip()
            )


            if (
                candidate_question
                .rstrip(
                    ".!?"
                )
                ==
                normalized_question
                .rstrip(
                    ".!?"
                )
            ):

                warnings.append(
                    f"dropped_question_echo_line:{number}"
                )

                continue


        if normalized_heading in (
            heading_values
        ):

            warnings.append(
                f"dropped_heading_line:{number}"
            )

            continue


        if any(
            phrase in normalized
            for phrase in placeholder_terms
        ):

            warnings.append(
                f"dropped_placeholder_line:{number}"
            )

            continue


        if (
            re.match(
                r"^\s*\d+\s*[.)-]\s*",
                stripped,
            )
            and any(
                phrase in normalized
                for phrase in instruction_echo_terms
            )
        ):

            warnings.append(
                f"dropped_instruction_echo_line:{number}"
            )

            continue


        if (
            "http://"
            in normalized
            or "https://"
            in normalized
            or "www."
            in normalized
        ):

            warnings.append(
                f"dropped_url_line:{number}"
            )

            continue


        if any(
            phrase in normalized
            for phrase in banned_advice
        ):

            warnings.append(
                f"dropped_advice_line:{number}"
            )

            continue


        produced_numbers = (
            _numeric_tokens(
                stripped
            )
        )


        unsupported = sorted(
            produced_numbers
            - allowed_numbers
        )


        if unsupported:

            warnings.append(
                (
                    "dropped_unsupported_numeric_line:"
                    + str(
                        number
                    )
                    + ":"
                    + ",".join(
                        unsupported
                    )
                )
            )

            continue


        # Remove any citation-like tokens
        # the model invents. Citations are
        # always attached by the system.
        stripped = re.sub(
            r"\[(?:E|K)\d+\]",
            "",
            stripped,
            flags=re.IGNORECASE,
        ).strip()


        if not stripped:
            continue


        # A generation can hit max_new_tokens
        # in the middle of the final sentence.
        # Only complete sentence content may
        # reach the user.

        if stripped[-1] not in ".!?":

            last_terminal = max(
                stripped.rfind("."),
                stripped.rfind("!"),
                stripped.rfind("?"),
            )


            if last_terminal >= 0:

                trimmed = (
                    stripped[
                        :last_terminal + 1
                    ]
                    .strip()
                )


                if trimmed != stripped:

                    warnings.append(
                        f"trimmed_incomplete_tail:{number}"
                    )


                stripped = trimmed

            else:

                warnings.append(
                    f"dropped_incomplete_line:{number}"
                )

                continue


        if not stripped:
            continue


        safe_lines.append(
            stripped
        )


    if not safe_lines:

        return (
            False,
            "",
            (
                "no_safe_line",
            ),
            tuple(
                warnings
            ),
        )


    return (
        True,
        "\n".join(
            safe_lines
        ),
        tuple(),
        tuple(
            warnings
        ),
    )


def _citation_suffix(
    evidence_group,
) -> str:

    ids = [
        str(
            item.evidence_id
        )
        for item in evidence_group
    ]


    return (
        "["
        + ", ".join(
            ids
        )
        + "]"
    )


def _attach_citations(
    text: str,
    *,
    evidence_group,
) -> str:

    suffix = (
        _citation_suffix(
            evidence_group
        )
    )


    result = []


    for line in str(
        text
        or ""
    ).splitlines():

        stripped = (
            line.strip()
        )

        if not stripped:
            continue


        result.append(
            stripped
            + " "
            + suffix
        )


    return "\n".join(
        result
    )


def _source_footer(
    context,
    cited_ids,
) -> str:

    wanted = set(
        cited_ids
    )

    groups = {}


    for item in context.evidence:

        evidence_id = str(
            item.evidence_id
        )


        if evidence_id not in wanted:
            continue


        key = (
            str(
                item.bank_name
            ),
            str(
                item.document_title
            ),
            str(
                item.source_url
            ),
            (
                None
                if item.checked_at is None
                else str(
                    item.checked_at
                )
            ),
        )


        groups.setdefault(
            key,
            [],
        ).append(
            evidence_id
        )


    rows = []


    for (
        bank,
        title,
        url,
        checked_at,
    ), ids in groups.items():

        row = (
            "- ["
            + ", ".join(
                ids
            )
            + "] "
            + bank
            + " - "
            + title
            + "\n  "
            + url
        )


        if checked_at:

            row += (
                "\n  Kontrol: "
                + checked_at
            )


        rows.append(
            row
        )


    if not rows:

        return ""


    return (
        "\n\nKaynaklar:\n"
        + "\n".join(
            rows
        )
    )


class LocalQwenRagGenerator:

    def __init__(
        self,
        *,
        model_id: str = (
            MODEL_ID_DEFAULT
        ),
        device: str = "cuda",
        max_new_tokens: int = 220,
    ):

        self.model_id = (
            model_id
        )

        self.device = (
            device
        )

        self.max_new_tokens = int(
            max_new_tokens
        )

        self._model = None
        self._tokenizer = None


    def load(
        self,
    ) -> None:

        if (
            self._model is not None
            and
            self._tokenizer is not None
        ):

            return


        import torch

        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
        )


        if (
            self.device == "cuda"
            and
            not torch.cuda.is_available()
        ):

            raise RuntimeError(
                "CUDA is not available."
            )


        self._tokenizer = (
            AutoTokenizer
            .from_pretrained(
                self.model_id,
                local_files_only=True,
            )
        )


        dtype = (
            torch.float16
            if self.device == "cuda"
            else torch.float32
        )


        self._model = (
            AutoModelForCausalLM
            .from_pretrained(
                self.model_id,
                dtype=dtype,
                low_cpu_mem_usage=True,
                local_files_only=True,
            )
            .to(
                self.device
            )
        )


        self._model.eval()


    def release(
        self,
    ) -> None:

        import torch

        self._model = None
        self._tokenizer = None

        gc.collect()

        if torch.cuda.is_available():

            torch.cuda.empty_cache()


    def _generate_one(
        self,
        context,
        evidence_group,
    ):

        import torch


        messages = (
            build_rag_generation_messages(
                context,
                evidence_group=(
                    evidence_group
                ),
            )
        )


        tokenizer = (
            self._tokenizer
        )

        model = (
            self._model
        )


        formatted = (
            tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
        )


        inputs = tokenizer(
            formatted,
            return_tensors="pt",
        )


        inputs = {
            key:
                value.to(
                    self.device
                )
            for key, value
            in inputs.items()
        }


        input_tokens = int(
            inputs[
                "input_ids"
            ].shape[-1]
        )


        if torch.cuda.is_available():

            torch.cuda.synchronize()


        started = (
            time.perf_counter()
        )


        with torch.inference_mode():

            output = model.generate(
                **inputs,
                max_new_tokens=(
                    self.max_new_tokens
                ),
                do_sample=False,
                repetition_penalty=1.05,
                pad_token_id=(
                    tokenizer.eos_token_id
                ),
            )


        if torch.cuda.is_available():

            torch.cuda.synchronize()


        elapsed = (
            time.perf_counter()
            - started
        )


        generated_ids = (
            output[
                0,
                input_tokens:
            ]
        )


        generated_tokens = int(
            generated_ids.shape[0]
        )


        raw = (
            tokenizer.decode(
                generated_ids,
                skip_special_tokens=True,
            )
            .strip()
        )


        return (
            raw,
            input_tokens,
            generated_tokens,
            elapsed,
        )


    def generate(
        self,
        context,
    ) -> RagGeneratedAnswer:

        if context.route not in (
            _ALLOWED_ROUTES
        ):

            raise ValueError(
                "Local RAG generator is allowed "
                "only for campaign_rag and "
                "product_rag."
            )


        if (
            context.answer_mode
            != "rag"
            or not context.may_generate_answer
        ):

            raise ValueError(
                "Grounded Answer Contract "
                "blocked RAG generation."
            )


        if not context.evidence:

            raise ValueError(
                "No selected evidence."
            )


        self.load()


        document_groups = (
            _group_evidence_by_document(
                context
            )
        )


        raw_parts = []

        safe_parts = []

        cited_ids = []

        warnings = []

        reasons = []

        total_input_tokens = 0

        total_generated_tokens = 0

        total_seconds = 0.0


        for group_index, group in enumerate(
            document_groups,
            start=1,
        ):

            (
                raw,
                input_tokens,
                generated_tokens,
                elapsed,
            ) = self._generate_one(
                context,
                group,
            )


            raw_parts.append(
                (
                    f"DOCUMENT_{group_index}\n"
                    + raw
                )
            )


            total_input_tokens += (
                input_tokens
            )

            total_generated_tokens += (
                generated_tokens
            )

            total_seconds += (
                elapsed
            )


            (
                passed,
                sanitized,
                group_reasons,
                group_warnings,
            ) = sanitize_document_answer(
                raw,
                evidence_group=group,
                question=context.question,
            )


            warnings.extend(
                (
                    f"doc{group_index}:"
                    + warning
                )
                for warning
                in group_warnings
            )


            if not passed:

                reasons.extend(
                    (
                        f"doc{group_index}:"
                        + reason
                    )
                    for reason
                    in group_reasons
                )

                continue


            cited = tuple(
                str(
                    item.evidence_id
                )
                for item in group
            )


            cited_ids.extend(
                cited
            )


            safe_parts.append(
                _attach_citations(
                    sanitized,
                    evidence_group=group,
                )
            )


        if safe_parts:

            passed_guard = True

            sanitized_final = (
                "\n".join(
                    safe_parts
                )
            )

            final_text = (
                sanitized_final
                + _source_footer(
                    context,
                    cited_ids,
                )
            )

            final_reasons = tuple()

        else:

            passed_guard = False

            sanitized_final = ""

            final_reasons = tuple(
                reasons
                or [
                    "no_safe_document_answer",
                ]
            )

            final_text = (
                "Do\u011frulanm\u0131\u015f kaynaklara "
                "ba\u011fl\u0131 g\u00fcvenli bir yan\u0131t "
                "\u00fcretilemedi. Yan\u0131t olu\u015fturma "
                "g\u00fcvenlik kontrol\u00fc devreye girdi."
            )


        unique_ids = []

        for value in cited_ids:

            if value not in unique_ids:

                unique_ids.append(
                    value
                )


        speed = (
            total_generated_tokens
            / total_seconds
            if total_seconds > 0
            else 0.0
        )


        return RagGeneratedAnswer(
            text=(
                final_text
            ),
            raw_model_text=(
                "\n\n".join(
                    raw_parts
                )
            ),
            sanitized_model_text=(
                sanitized_final
            ),
            passed_guard=(
                passed_guard
            ),
            cited_evidence_ids=tuple(
                unique_ids
            ),
            allowed_evidence_ids=tuple(
                str(
                    item.evidence_id
                )
                for item in context.evidence
            ),
            guard_reasons=(
                final_reasons
            ),
            guard_warnings=tuple(
                warnings
            ),
            model_id=(
                self.model_id
            ),
            input_tokens=(
                total_input_tokens
            ),
            generated_tokens=(
                total_generated_tokens
            ),
            generation_seconds=(
                total_seconds
            ),
            tokens_per_second=(
                speed
            ),
        )
