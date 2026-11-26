// Rodapé: o aviso legal (P9), os termos de uso e a privacidade (C2), e as versões dos motores oficiais em execução
// (checklist da seção 21 do plano).

import { useModo } from '../sessao/ganchos.ts';
import { AVISO_LEGAL } from './aviso.ts';
import { Link } from './navegacao.tsx';

const NOME_DO_MOTOR = {
  regime_regular: 'Regime regular',
  simples_nacional: 'Simples Nacional',
} as const;

export function Rodape() {
  const modo = useModo();
  return (
    <footer className="rodape">
      <div className="coluna rodape__linha">
        <p>{AVISO_LEGAL}</p>
        <ul className="rodape__links" aria-label="Documentos">
          <li>
            <Link para="/termos">Termos de uso</Link>
          </li>
          <li>
            <Link para="/privacidade">Privacidade</Link>
          </li>
        </ul>
        {modo.tipo === 'pronto' && modo.saude.motores.length > 0 && (
          <ul className="rodape__motores" aria-label="Motores oficiais">
            {modo.saude.motores.map((motor) => (
              <li key={motor.motor}>
                {NOME_DO_MOTOR[motor.motor]}{' '}
                <span className="num">{motor.versaoEmExecucao ?? motor.versaoFixada}</span>
                {motor.banco !== null && motor.banco !== undefined && (
                  <>
                    {' '}
                    · banco <span className="num">{motor.banco}</span>
                  </>
                )}
                {!motor.ok && <> · fora do ar</>}
                {motor.ok && !motor.coerente && <> · versão diferente da fixada</>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </footer>
  );
}
