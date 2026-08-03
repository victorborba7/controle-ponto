"""Schemas da configuracao de batida.

Dois publicos, dois formatos:

- **RH** monta a configuracao (`PunchConfigUpdate`) e ve tudo, inclusive
  rotulos desativados.
- **App** so precisa saber o que desenhar na tela (`PunchFormConfig`), e recebe
  apenas os rotulos ativos, ja na ordem. Mandar o resto vazaria a estrutura
  interna sem serventia nenhuma para quem esta batendo o ponto.
"""

import uuid
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import EntryType, LabelMode, NoteMode
from app.models.punch_config import LABEL_MAX_LENGTH

#: Teto de opcoes por empresa. Nao e limite tecnico: e a tela do funcionario,
#: que vira uma parede de botoes muito antes disso.
MAX_LABELS = 20


class PunchLabelInput(BaseModel):
    """Uma opcao de rotulo, como o RH a envia."""

    name: str = Field(min_length=1, max_length=LABEL_MAX_LENGTH)
    entry_type: EntryType
    is_active: bool = True


class PunchLabelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    entry_type: EntryType
    position: int
    is_active: bool


class PunchConfigUpdate(BaseModel):
    """Configuracao completa. O PUT substitui, nao mescla.

    Substituir e o que torna a ordem dos rotulos editavel sem inventar um
    endpoint de reordenacao: a posicao e o indice na lista enviada.
    """

    note_mode: NoteMode = NoteMode.HIDDEN
    note_prompt: str | None = Field(default=None, max_length=120)
    label_mode: LabelMode = LabelMode.HIDDEN
    label_required: bool = False
    labels: list[PunchLabelInput] = Field(default_factory=list, max_length=MAX_LABELS)

    @model_validator(mode="after")
    def _coerente(self) -> Self:
        nomes = [rotulo.name.strip().casefold() for rotulo in self.labels]
        if len(nomes) != len(set(nomes)):
            raise ValueError("Ha rotulos repetidos; cada nome tem de ser unico.")
        if any(not nome for nome in nomes):
            raise ValueError("Rotulo sem nome.")

        # Modo lista sem opcao ativa deixaria o funcionario travado numa tela
        # de escolha sem nada para escolher.
        if self.label_mode is LabelMode.LIST and not any(r.is_active for r in self.labels):
            raise ValueError("O modo de lista precisa de ao menos uma opcao ativa.")

        # Exigir o que nao aparece travaria a batida sem saida pela interface.
        if self.label_required and self.label_mode is LabelMode.HIDDEN:
            raise ValueError("Nao da para exigir o tipo da batida sem exibi-lo.")
        return self


class PunchConfigOut(BaseModel):
    """Visao do painel: a configuracao inteira, rotulos inativos inclusive."""

    note_mode: NoteMode
    note_prompt: str | None
    label_mode: LabelMode
    label_required: bool
    labels: list[PunchLabelOut]


class PunchFormLabel(BaseModel):
    """Uma opcao como o app a exibe.

    Sem `entry_type` de proposito: o funcionario escolhe pelo nome, e o
    servidor traduz. Mandar o tipo junto convidaria o app a decidir jornada,
    que e decisao do RH.
    """

    name: str


class PunchFormConfig(BaseModel):
    """O que o app precisa para montar a tela de batida."""

    note_mode: NoteMode
    #: Texto que o RH quer ver acima do campo ("Justifique o atraso").
    note_prompt: str | None
    label_mode: LabelMode
    label_required: bool
    labels: list[PunchFormLabel]
