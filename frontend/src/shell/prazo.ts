// Quanto falta para o espaço vencer, em palavras curtas ("1 h 52 min").

const MINUTO = 60_000;

export function formatarPrazo(restanteMs: number): string {
  if (restanteMs < MINUTO) {
    return 'menos de 1 min';
  }
  const minutos = Math.floor(restanteMs / MINUTO);
  const horas = Math.floor(minutos / 60);
  const resto = minutos % 60;
  if (horas === 0) {
    return `${String(resto)} min`;
  }
  return resto === 0 ? `${String(horas)} h` : `${String(horas)} h ${String(resto)} min`;
}
