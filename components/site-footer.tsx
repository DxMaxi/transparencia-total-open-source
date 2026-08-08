import { LandmarkIcon } from "@/components/icons";

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="shell footer-grid">
        <div>
          <div className="footer-brand"><LandmarkIcon /> Transparência Total / Fator Cívico</div>
          <p>
            Projeto cívico, neutro, sem fins lucrativos e de código aberto.
            Cada afirmação publicável exige uma fonte oficial auditável.
          </p>
        </div>
        <div>
          <strong>Projeto</strong>
          <a href="/metodologia">Metodologia</a>
          <a href="/direito-de-resposta">Direito de resposta</a>
          <a href="/investigador">Investigador Cívico</a>
          <a href="/atividade-parlamentar">Atividade parlamentar</a>
          <a href="https://github.com/DxMaxi/transparencia-total-open-source" target="_blank" rel="noreferrer">Código-fonte</a>
          <a href="/metodologia#neutralidade">Política de neutralidade</a>
        </div>
        <div>
          <strong>Fontes oficiais</strong>
          <a href="https://www.parlamento.pt/Cidadania/Paginas/DadosAbertos.aspx" target="_blank" rel="noreferrer">Assembleia da República</a>
          <a href="https://diariodarepublica.pt/" target="_blank" rel="noreferrer">Diário da República</a>
          <a href="https://www.tribunalconstitucional.pt/tc/ept/" target="_blank" rel="noreferrer">Entidade para a Transparência</a>
        </div>
      </div>
      <div className="shell footer-bottom">
        <span>Licença MIT · Dados oficiais pertencem às entidades de origem</span>
        <span>Interface em português de Portugal</span>
      </div>
    </footer>
  );
}
