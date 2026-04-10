export interface Gasto {
  id: string;
  fecha: string;
  descripcion: string;
  monto: number;
  categoria: string;
  comprobante_url?: string;
  infraestructura?: { nombre: string };
}

export interface Balance {
  total_ingresos: number;
  total_gastos: number;
  balance: number;
}

export interface Ingreso {
  id: string;
  fecha: string;
  descripcion: string;
  monto: number;
  fuente: string;
  comprobante_url?: string;
  pagador?: string;
}
