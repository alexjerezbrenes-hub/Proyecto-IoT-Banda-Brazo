package backend.repository;

import backend.model.Dato;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DatoRepository extends JpaRepository<Dato, Long> {
}
