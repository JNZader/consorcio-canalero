"""
PDF Generation Service.
Creates professional reports for the Consorcio.
"""

import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.units import cm

class PDFService:
    def create_emergency_report(self, data: dict) -> io.BytesIO:
        """
        Generate a professional PDF report about the current situation.
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, 
            pagesize=A4, 
            rightMargin=1.5*cm, 
            leftMargin=1.5*cm, 
            topMargin=1.5*cm, 
            bottomMargin=1.5*cm
        )
        styles = getSampleStyleSheet()
        
        # Colors
        PRIMARY_BLUE = colors.hexColor("#1971c2")
        LIGHT_BG = colors.hexColor("#f8f9fa")
        BORDER_COLOR = colors.hexColor("#dee2e6")
        
        # Custom styles
        title_style = ParagraphStyle(
            'ReportTitle',
            parent=styles['Heading1'],
            fontSize=22,
            textColor=PRIMARY_BLUE,
            alignment=1, # Center
            spaceAfter=20
        )
        
        header_label = ParagraphStyle(
            'HeaderLabel',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.grey,
            alignment=2 # Right
        )
        
        section_title = ParagraphStyle(
            'SectionTitle',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=PRIMARY_BLUE,
            spaceBefore=15,
            spaceAfter=10,
            borderPadding=5,
            borderColor=PRIMARY_BLUE,
            borderWidth=0,
            leftIndent=0
        )
        
        story = []
        
        # --- Institutional Header ---
        header_table_data = [
            [
                Paragraph("<b>CONSORCIO CANALERO</b><br/>10 de Mayo", styles['Normal']),
                Paragraph(f"INFORME TÉCNICO DE SITUACIÓN<br/>{datetime.now().strftime('%d/%m/%Y %H:%M')}", header_label)
            ]
        ]
        ht = Table(header_table_data, colWidths=[9*cm, 9*cm])
        ht.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('LINEBELOW', (0, 0), (-1, -1), 1, PRIMARY_BLUE),
        ]))
        story.append(ht)
        story.append(Spacer(1, 20))
        
        # Main Title
        story.append(Paragraph(f"Estado de Cuencas: {data.get('cuenca', 'Zona Consorcio')}", title_style))
        
        # --- Summary Stats Table ---
        story.append(Paragraph("Resumen de Afectación Satelital", section_title))
        summary_data = [
            ["Cuenca", "Superficie (ha)", "Anegamiento (%)", "Nivel de Riesgo"],
        ]
        for row in data.get('stats', []):
            risk_color = colors.green
            if row['pct'] > 20: risk_color = colors.red
            elif row['pct'] > 10: risk_color = colors.orange
            
            summary_data.append([
                row['nombre'], 
                f"{row['ha']:,}", 
                f"{row['pct']}%", 
                Paragraph(f"<b>{row['estado']}</b>", ParagraphStyle('risk', textColor=risk_color, alignment=1))
            ])
            
        t = Table(summary_data, colWidths=[5.5*cm, 4*cm, 4*cm, 4.5*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), PRIMARY_BLUE),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('TOPPADDING', (0, 0), (-1, 0), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
        ]))
        story.append(t)
        
        # --- Maintenance Section ---
        if data.get('recent_maintenance'):
            story.append(Paragraph("Bitácora de Mantenimiento Reciente", section_title))
            maint_data = [["Fecha", "Infraestructura", "Tarea Realizada", "Estado Final"]]
            for m in data['recent_maintenance']:
                maint_data.append([m['fecha'], m['nombre'], m['tarea'], m['estado']])
            
            mt = Table(maint_data, colWidths=[3*cm, 5*cm, 7*cm, 3*cm])
            mt.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.hexColor("#e9ecef")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.darkslategrey),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ]))
            story.append(mt)

        # Footer on every page (Build logic)
        def footer(canvas, doc):
            canvas.saveState()
            canvas.setFont('Helvetica', 8)
            canvas.setStrokeColor(PRIMARY_BLUE)
            canvas.line(1.5*cm, 1*cm, 19.5*cm, 1*cm)
            canvas.drawString(1.5*cm, 0.7*cm, "Consorcio Canalero 10 de Mayo - Bell Ville, Córdoba")
            canvas.drawRightString(19.5*cm, 0.7*cm, f"Página {doc.page}")
            canvas.restoreState()

        # Build PDF
        doc.build(story, onFirstPage=footer, onLaterPages=footer)
        buffer.seek(0)
        return buffer

    def create_agenda_pdf(self, reunion: dict, agenda: list) -> io.BytesIO:
        """
        Generate a professional Order of the Day / Agenda for a meeting.
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, 
            pagesize=A4, 
            rightMargin=2*cm, 
            leftMargin=2*cm, 
            topMargin=2*cm, 
            bottomMargin=2*cm
        )
        styles = getSampleStyleSheet()
        
        # Colors
        PRIMARY_BLUE = colors.hexColor("#1971c2")
        VIOLET = colors.hexColor("#7950f2")
        
        # Styles
        title_style = ParagraphStyle(
            'Title', parent=styles['Heading1'], fontSize=20, textColor=VIOLET, alignment=1, spaceAfter=20
        )
        item_title = ParagraphStyle(
            'ItemTitle', parent=styles['Heading2'], fontSize=12, textColor=colors.black, spaceBefore=10
        )
        ref_style = ParagraphStyle(
            'RefStyle', parent=styles['Normal'], fontSize=9, textColor=colors.grey, leftIndent=10
        )

        story = []
        
        # Header
        story.append(Paragraph("ORDEN DEL DÍA", title_style))
        story.append(Paragraph(f"<b>Reunión:</b> {reunion['titulo']}", styles['Normal']))
        story.append(Paragraph(f"<b>Fecha:</b> {reunion['fecha_reunion']}", styles['Normal']))
        story.append(Paragraph(f"<b>Lugar:</b> {reunion['lugar']}", styles['Normal']))
        story.append(Spacer(1, 10))
        # Draw a line
        line_table = Table([[""]], colWidths=[17*cm])
        line_table.setStyle(TableStyle([('LINEBELOW', (0,0), (-1,-1), 1, colors.grey)]))
        story.append(line_table)
        story.append(Spacer(1, 10))
        
        # Agenda Items
        story.append(Paragraph("Temas a Tratar", styles['Heading2']))
        story.append(Spacer(1, 10))

        for i, item in enumerate(agenda):
            story.append(Paragraph(f"{i+1}. {item['titulo']}", item_title))
            if item.get('descripcion'):
                story.append(Paragraph(item['descripcion'], styles['Normal']))
            
            # Show references if any
            if item.get('referencias'):
                story.append(Spacer(1, 5))
                for ref in item['referencias']:
                    label = ref.get('metadata', {}).get('label', f"{ref['entidad_tipo']} #{ref['entidad_id'][:5]}")
                    story.append(Paragraph(f"• Vinculado con: {label}", ref_style))
            
            story.append(Spacer(1, 10))

        # Build PDF
        doc.build(story)
        buffer.seek(0)
        return buffer

    def create_asset_ficha_pdf(self, asset: dict, history: list) -> io.BytesIO:
        """PDF A: Ficha Técnica de un Activo (Alcantarilla/Puente)."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, margin=1.5*cm)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph(f"FICHA TÉCNICA: {asset['nombre']}", ParagraphStyle('T', parent=styles['Heading1'], alignment=1)))
        story.append(Spacer(1, 10))
        
        # Info Table
        data = [
            ["Tipo de Activo:", asset['tipo'].upper(), "Estado Actual:", asset['estado_actual'].upper()],
            ["Cuenca:", asset['cuenca'], "Coordenadas:", f"{asset['latitud']}, {asset['longitud']}"]
        ]
        t = Table(data, colWidths=[4*cm, 5*cm, 4*cm, 5*cm])
        t.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.grey), ('BACKGROUND', (0,0), (0,-1), colors.whitesmoke)]))
        story.append(t)
        
        story.append(Paragraph("Historial de Mantenimiento", styles['Heading2']))
        if not history:
            story.append(Paragraph("No hay registros de mantenimiento.", styles['Normal']))
        else:
            h_data = [["Fecha", "Tarea", "Operario", "Descripción"]]
            for h in history:
                h_data.append([h['fecha'][:10], h['tipo_tarea'], h.get('operario_nombre', '-'), h['descripcion']])
            ht = Table(h_data, colWidths=[3*cm, 3*cm, 4*cm, 8*cm])
            ht.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.grey), ('BACKGROUND', (0,0), (-1,0), colors.lightgrey)]))
            story.append(ht)

        doc.build(story)
        buffer.seek(0)
        return buffer

    def create_tramite_summary_pdf(self, tramite: dict, avances: list) -> io.BytesIO:
        """PDF B: Resumen de Expediente/Trámite Provincial."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph(f"EXPEDIENTE: {tramite['numero_expediente'] or 'S/N'}", styles['Heading1']))
        story.append(Paragraph(f"<b>Título:</b> {tramite['titulo']}", styles['Normal']))
        story.append(Paragraph(f"<b>Estado:</b> {tramite['estado'].upper()}", styles['Normal']))
        story.append(Spacer(1, 20))

        story.append(Paragraph("Línea de Tiempo de Avances", styles['Heading2']))
        for a in avances:
            story.append(Paragraph(f"<b>{a['fecha'][:10]} - {a['titulo_avance']}</b>", styles['Normal']))
            story.append(Paragraph(a['comentario'], ParagraphStyle('C', leftIndent=20, fontSize=9)))
            story.append(Spacer(1, 5))

        doc.build(story)
        buffer.seek(0)
        return buffer

    def create_report_resolution_pdf(self, reporte: dict, seguimiento: list) -> io.BytesIO:
        """PDF C: Comprobante de Resolución de Reporte para el vecino."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph("CONSTANCIA DE RESOLUCIÓN", ParagraphStyle('T', fontSize=18, alignment=1)))
        story.append(Spacer(1, 20))
        story.append(Paragraph(f"Por la presente se informa que el reporte ID #{reporte['id'][:8]}, categorizado como <b>{reporte['categoria']}</b> y ubicado en <b>{reporte['ubicacion_texto']}</b>, ha sido dado por FINALIZADO.", styles['Normal']))
        
        story.append(Paragraph("Resumen de Gestión", styles['Heading2']))
        for s in seguimiento:
            if s['comentario_publico']:
                story.append(Paragraph(f"• {s['fecha'][:10]}: {s['comentario_publico']}", styles['Normal']))

        story.append(Spacer(1, 40))
        story.append(Paragraph("__________________________<br/>Comisión Directiva<br/>Consorcio Canalero 10 de Mayo", ParagraphStyle('S', alignment=1)))

        doc.build(story)
        buffer.seek(0)
        return buffer

    def create_general_impact_report_pdf(self, data: dict) -> io.BytesIO:
        """PDF D: Informe de Gestión Integral (Satelital + Reportes + Sugerencias)."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, margin=1*cm)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph("INFORME DE GESTIÓN INTEGRAL", ParagraphStyle('T', fontSize=22, textColor=colors.hexColor("#1971c2"), alignment=1)))
        story.append(Spacer(1, 20))

        # Satélite
        story.append(Paragraph("1. Estado de Cuencas (Análisis Satelital)", styles['Heading2']))
        s_data = [["Cuenca", "Anegamiento %", "Estado"]]
        for s in data['satelite']:
            s_data.append([s['nombre'], f"{s['pct']}%", s['estado']])
        st = Table(s_data, colWidths=[6*cm, 6*cm, 6*cm])
        st.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.grey), ('BACKGROUND', (0,0), (-1,0), colors.hexColor("#e7f5ff"))]))
        story.append(st)

        # Reportes y Sugerencias por Cuenca
        story.append(Paragraph("2. Gestión Comunitaria por Cuenca", styles['Heading2']))
        for cuenca, info in data['cuencas_data'].items():
            story.append(Paragraph(f"<b>Cuenca {cuenca.capitalize()}</b>", styles['Normal']))
            story.append(Paragraph(f"• Reportes activos: {info['reportes_count']}", styles['Normal']))
            story.append(Paragraph(f"• Sugerencias recibidas: {info['sugerencias_count']}", styles['Normal']))
            story.append(Spacer(1, 5))

        doc.build(story)
        buffer.seek(0)
        return buffer

_pdf_service = None

def get_pdf_service() -> PDFService:
    global _pdf_service
    if _pdf_service is None:
        _pdf_service = PDFService()
    return _pdf_service
