// A marca do ContaAI: o símbolo (o mesmo desenho do favicon, public/favicon.svg: quadrado preto com o "C"
// branco) à esquerda do nome. Na barra preta, o quadrado leva um contorno branco fino para não sumir no fundo.

export function Simbolo() {
  return (
    <svg className="marca__simbolo" viewBox="0 0 32 32" width="24" height="24" aria-hidden="true" focusable="false">
      <rect x="0.75" y="0.75" width="30.5" height="30.5" rx="6" className="marca__quadrado" />
      <path d="M22 11.5a7 7 0 1 0 0 9" fill="none" stroke="#ffffff" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function Marca() {
  return (
    <>
      <Simbolo />
      <span>ContaAI</span>
    </>
  );
}
