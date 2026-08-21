/**
 * Registro do aparelho para receber os lembretes horários.
 *
 * O lembrete é decidido e enviado pelo **servidor** — o app só informa onde
 * entregar. Foi decisão de projeto: assim o RH pode mudar a regra sem exigir
 * que 10 pessoas atualizem o app, e o envio fica auditável.
 *
 * ## Por que nada trava se isto falhar
 *
 * Lembrete é conveniência; bater ponto é a função. Permissão negada, aparelho
 * sem rede ou serviço do Expo fora do ar não podem impedir ninguém de
 * registrar a jornada — todo o caminho aqui falha em silêncio e segue.
 */

import * as Notifications from "expo-notifications";

import { autenticado } from "./api";

/**
 * Como a notificação aparece com o app aberto.
 *
 * Sem isto, o iOS entrega em silêncio quando o app está em primeiro plano — e
 * o funcionário com o app aberto na tela de ponto é justamente quem mais
 * precisa ver o lembrete.
 */
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

/**
 * Pede permissão, obtém o token e registra no servidor.
 *
 * Chamado depois do login. Reenviar a cada acesso é de propósito: o token do
 * Expo rotaciona sozinho em reinstalação e restauração de backup, e um token
 * velho no banco vira lembrete entregue a ninguém.
 */
export async function registrarParaLembretes(): Promise<boolean> {
  try {
    const token = await obterToken();
    if (!token) return false;

    const resposta = await autenticado("/auth/me/push-token", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ push_token: token }),
    });

    return resposta.ok;
  } catch {
    return false;
  }
}

async function obterToken(): Promise<string | null> {
  const atual = await Notifications.getPermissionsAsync();

  // Só pede se ainda não foi decidido. Insistir com quem já negou não muda
  // nada — o sistema nem exibe o diálogo de novo — e no Android reabriria uma
  // pergunta que a pessoa já respondeu.
  let concedida = atual.granted;
  if (!concedida && atual.canAskAgain) {
    concedida = (await Notifications.requestPermissionsAsync()).granted;
  }
  if (!concedida) return null;

  const resultado = await Notifications.getExpoPushTokenAsync();
  return resultado.data ?? null;
}
