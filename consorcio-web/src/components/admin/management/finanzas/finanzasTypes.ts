export interface Gasto {
  id: string;
  fecha: string;
  descripcion: string;
  monto: number;
  categoria: string;
  proveedor?: string | null;
  created_at: string;
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
  categoria: string;
  consorcista_id?: string | null;
  created_at: string;
}
