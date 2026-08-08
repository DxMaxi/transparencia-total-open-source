import { LandmarkIcon } from "@/components/icons";
import { CONTACT_EMAIL, LEGAL_RESPONSIBLE } from "@/lib/site";

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="shell footer-grid">
        <div>
          <div className="footer-brand"><LandmarkIcon /> Transparência Total / Fator Cívico</div>
          <p>
            Projeto cívico independente, sem publicidade e sem filiação partidária.
            Não é um website oficial do Estado.
          </p>
          <span className="footer-responsible">Responsável: {LEGAL_RESPONSIBLE}</span>
          <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>
        </div>
        <div>
          <strong>Projeto</strong>
          <a href="/metodologia">Metodologia</a>
          <a href="/direito-de-resposta">Direito de resposta</a>
          <a href="/atividade-parlamentar">Atividade parlamentar</a>
          <a href="/promessas">Promessómetro</a>
          <a href="/contacto">Contacto</a>
        </div>
        <div>
          <strong>Informação legal</strong>
          <a href="/privacidade">Privacidade</a>
          <a href="/cookies">Cookies</a>
          <a href="/termos">Termos e aviso legal</a>
          <a href="/acessibilidade">Acessibilidade</a>
          <a href="/metodologia#neutralidade">Política de neutralidade</a>
        </div>
        <div>
          <strong>Fontes oficiais</strong>
          <a href="https://www.parlamento.pt/Cidadania/Paginas/DadosAbertos.aspx" target="_blank" rel="noreferrer noopener">Assembleia da República</a>
          <a href="https://diariodarepublica.pt/" target="_blank" rel="noreferrer noopener">Diário da República</a>
          <a href="https://portugal.gov.pt/gc25/governo/programa-do-governo" target="_blank" rel="noreferrer noopener">Programa do Governo</a>
          <a href="https://www.tribunalconstitucional.pt/tc/ept/" target="_blank" rel="noreferrer noopener">Entidade para a Transparência</a>
        </div>
      </div>
      <div className="shell footer-bottom">
        <span>Interface em português de Portugal · Dados pertencem às entidades de origem</span>
        <span>Informação pública, não aconselhamento profissional</span>
      </div>
    </footer>
  );
}
