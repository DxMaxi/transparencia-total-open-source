import { SourceLink } from "@/components/source-link";
import type { PublicPoliticianDirectory as DirectoryData } from "@/types/public-data";

const roleLabels: Record<string, string> = {
  DEPUTY: "Deputado/a",
  MINISTER: "Ministro/a",
  SECRETARY_OF_STATE: "Secretário/a de Estado",
  MAYOR: "Presidente de Câmara",
  OTHER_PUBLIC_OFFICE: "Titular de cargo público",
};

const numberFormatter = new Intl.NumberFormat("pt-PT");

function formatCount(directory: DirectoryData): string {
  const visible = numberFormatter.format(directory.people.length);
  if (!directory.totalIsExact) {
    return `${visible} perfis nesta página · total ainda não confirmado`;
  }
  const total = numberFormatter.format(directory.total);
  if (directory.people.length === directory.total) {
    return `${total} ${directory.total === 1 ? "perfil publicado" : "perfis publicados"}`;
  }
  return `A mostrar ${visible} de ${total} perfis publicados`;
}

export function PoliticianDirectory({
  directory,
  nextHref,
  previousHref,
}: {
  directory: DirectoryData;
  nextHref?: string;
  previousHref?: string;
}) {
  const hasFilters = Boolean(directory.query || directory.partyShort);
  const unavailable = directory.compatibilityMode === "UNAVAILABLE";

  return (
    <section id="diretorio" aria-label="Perfis disponíveis">
      <form className="directory-controls card" action="/politicos#diretorio" method="get">
        <label>
          <span>Pesquisar no diretório publicado</span>
          <input
            type="search"
            name="q"
            defaultValue={directory.query}
            maxLength={120}
            placeholder="Nome, partido ou círculo eleitoral"
          />
        </label>
        <label>
          <span>Grupo indicado na fonte</span>
          <select name="grupo" defaultValue={directory.partyShort ?? ""}>
            <option value="">Todos os grupos</option>
            {directory.parties.map((item) => (
              <option value={item.value} key={item.value}>
                {item.value} — {item.label} ({numberFormatter.format(item.count)})
              </option>
            ))}
          </select>
        </label>
        <div className="directory-controls__actions">
          <button className="button button--primary" type="submit">Pesquisar</button>
          {hasFilters ? <a className="text-link" href="/politicos#diretorio">Limpar</a> : null}
        </div>
        <strong aria-live="polite">{formatCount(directory)}</strong>
      </form>

      <p className="directory-search-rule">{directory.searchRule}</p>
      {directory.compatibilityMode === "LEGACY_LIMITED" ? (
        <div className="notice notice--warning" role="status">
          <strong>Consulta parcial.</strong>{" "}
          A API ainda não confirmou que devolveu o diretório completo. O total permanece
          indisponível até essa confirmação existir.
        </div>
      ) : null}

      {directory.people.length ? (
        <div className="politician-directory">
          {directory.people.map((person) => (
            <article className="politician-directory__card card" key={person.id}>
              <div className="profile-avatar" aria-hidden="true">{person.partyShort.slice(0, 3)}</div>
              <div>
                <span className="eyebrow">
                  {roleLabels[person.role] ?? person.role.replaceAll("_", " ")}
                </span>
                <h2><a href={`/politicos/${person.slug}`}>{person.name}</a></h2>
                <p>
                  Grupo observado: {person.partyShort} — {person.party} · Círculo: {person.constituency}
                  {" · "}{person.legislature}
                </p>
                <small className="directory-observation-date">
                  Observado na fonte em {person.observedAt} · revisto em {person.verifiedAt}
                </small>
                <SourceLink source={person.profileSource} compact />
              </div>
              <a className="text-link" href={`/politicos/${person.slug}`}>Abrir ficha</a>
            </article>
          ))}
        </div>
      ) : (
        <div className="empty-state card">
          <strong>
            {unavailable
              ? "Diretório temporariamente indisponível"
              : hasFilters
                ? "Nenhum perfil corresponde à pesquisa"
                : "Ainda não existem perfis publicáveis"}
          </strong>
          <span>
            {unavailable
              ? "Não apresentamos uma lista antiga ou não confirmada como substituição."
              : hasFilters
                ? "Altere o nome ou o grupo indicado na fonte."
                : "A ausência de perfis publicados não significa ausência de titulares de cargos."}
          </span>
        </div>
      )}

      {previousHref || nextHref ? (
        <nav className="politician-pagination" aria-label="Paginação do diretório de políticos">
          {previousHref ? (
            <a href={previousHref}>
              {directory.paginationMode === "CURSOR" ? "Voltar ao início" : "Página anterior"}
            </a>
          ) : <span />}
          <strong>{formatCount(directory)}</strong>
          {nextHref ? <a href={nextHref}>Ver mais perfis</a> : <span />}
        </nav>
      ) : null}
    </section>
  );
}
