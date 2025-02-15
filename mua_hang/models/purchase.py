from odoo import models, fields, api
from odoo.exceptions import UserError
from io import BytesIO
import xlsxwriter
import base64


class Purchase(models.Model):
    _name = "purchase.request"
    _description = "Purchase Request"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Yêu cầu tham chiếu", required=True, readonly=True, default="New")
    department_id = fields.Many2one('hr.department', string='Phòng ban', required=True,
                                    default=lambda self: self._get_default_department())
    request_id = fields.Many2one('res.users', string='Được yêu cầu bởi', required=True,
                                 default=lambda self: self.env.user.id)
    approver_id = fields.Many2one('res.users', string='Người phê duyệt', readonly=True)
    date = fields.Date(string='Ngày yêu cầu', default=fields.Date.context_today)
    date_approve = fields.Date(string='Ngày phê duyệt', readonly=True)
    request_line_ids = fields.One2many('purchase.request.line', 'request_id', string='Chi tiết yêu cầu mua hàng',
                                       required=True)
    description = fields.Text(string='Mô tả')
    state = fields.Selection([
        ('draft', 'Dự thảo'),
        ('wait', 'Chờ phê duyệt'),
        ('approved', 'Đã phê duyệt'),
        ('cancel', 'Đã hủy'),
    ], string='Trạng thái', default='draft')
    total_qty = fields.Float(string='Tổng số lượng', compute='_compute_total_qty', store=True)
    total_amount = fields.Float(string='Tổng giá trị', compute='_compute_total_amount', store=True)
    reject_reason = fields.Text(string='Lý do từ chối')
    priority = fields.Selection(
        [('0', 'Normal'), ('1', 'Urgent')], 'Priority', default='0', index=True)

    # PR + số tự sinh của name
    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('purchase.request.sequence') or 'New'
        return super(Purchase, self).create(vals)

    # Mặc định phòng ban của người dùng
    @api.model
    def _get_default_department(self):
        # Lấy nhân viên liên kết với người dùng hiện tại
        employee = self.env['hr.employee'].search([('user_id', '=', self.env.user.id)], limit=1)
        return employee.department_id.id if employee and employee.department_id else False

    # Tổng số lượng
    @api.depends('request_line_ids.qty')
    def _compute_total_qty(self):
        for record in self:
            record.total_qty = sum(line.qty for line in record.request_line_ids)

    # Tổng giá trị
    @api.depends('request_line_ids.total')
    def _compute_total_amount(self):
        for record in self:
            record.total_amount = sum(line.total for line in record.request_line_ids)

    # Gửi yêu cầu dự thảo
    def action_submit(self):
        for record in self:
            if record.state != 'draft':
                raise UserError("Chỉ có thể gửi yêu cầu ở trạng thái dự thảo.")
            record.state = 'wait'

    # Quay lại yêu cầu dự thảo
    def action_reset_to_draft(self):
        for record in self:
            if record.state != 'wait':
                raise UserError("Chỉ có thể quay lại từ trạng thái chờ phê duyệt.")
            record.state = 'draft'

    # Phê duyệt yêu cầu dự thảo
    def action_approve(self):
        for record in self:
            if record.state != 'wait':
                raise UserError("Chỉ có thể phê duyệt yêu cầu ở trạng thái chờ phê duyệt.")
            record.state = 'approved'
            record.date_approve = fields.Date.context_today(self)
            record.approver_id = self.env.user.id
            record.state = 'approved'

    # Huỷ yêu cầu dự thảo
    def action_cancel(self):
        return {
            'name': 'Lý do từ chối',
            'type': 'ir.actions.act_window',
            'res_model': 'reject.reason.wizard',
            'view_mode': 'form',
            'target': 'new',  # Mở popup wizard
            'context': {'default_reject_reason': ''},
        }

    def action_view_invoice(self):
        pass

    # Không xoá bản ghi khác dự thảo
    def unlink(self):
        for record in self:
            if record.state != 'draft':
                raise UserError("Bạn không được phép xóa ở trạng thái khác dự thảo.")
            record.request_line_ids.unlink()
        return super(Purchase, self).unlink()

    # Xuất excel
    def export_to_excel(self):
        for record in self:
            # Tạo file Excel
            output = BytesIO()
            workbook = xlsxwriter.Workbook(output)
            worksheet = workbook.add_worksheet("Yêu cầu mua hàng")
            # Định dạng cột
            bold = workbook.add_format({"bold": True})
            worksheet.write(0, 0, "Sản phẩm", bold)
            worksheet.write(0, 1, "Số lượng", bold)
            worksheet.write(0, 2, "Đơn vị tính", bold)
            worksheet.write(0, 3, "Tổng giá trị", bold)

            # Ghi dữ liệu
            row = 1
            for line in record.request_line_ids:
                worksheet.write(row, 0, line.product_id.name)
                worksheet.write(row, 1, line.qty)
                worksheet.write(row, 2, line.uom_id.name)
                worksheet.write(row, 3, line.total)
                row += 1

            # Đóng workbook
            workbook.close()
            output.seek(0)

            # Lưu file
            file_data = base64.b64encode(output.read())
            output.close()

            # Tạo attachment
            attachment = self.env['ir.attachment'].create({
                'name': 'purchase_request.xlsx',
                'type': 'binary',
                'datas': file_data,
                'store_fname': 'purchase_request.xlsx',
                'mimetype': 'application/vnd.ms-excel',
            })

            # Trả về liên kết tải về
            return {
                'type': 'ir.actions.act_url',
                'url': f'/web/content/{attachment.id}?download=true',
                'target': 'new',
            }

    # Gửi mail
    def send_email_to_creator(self):
        """Open email composition wizard with preloaded template."""
        self.ensure_one()
        template_id = self.env.ref('mua_hang.email_template_purchase_request_2').id
        compose_form_id = self.env.ref('mail.email_compose_message_wizard_form').id

        ctx = {
            'default_model': 'purchase.request',
            'default_res_ids': [self.id],
            'default_template_id': template_id,
            'default_composition_mode': 'comment',
            'force_email': True,
        }

        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(compose_form_id, 'form')],
            'view_id': compose_form_id,
            'target': 'new',
            'context': ctx,
        }


class PurchaseLine(models.Model):
    _name = "purchase.request.line"
    _description = "Purchase Request Line"

    request_id = fields.Many2one('purchase.request', sring='Yêu cầu mua hàng')
    product_id = fields.Many2one('product.template', string='Sản phẩm', required=True)
    uom_id = fields.Many2one('uom.uom', string='Đơn vị tính', required=True)
    qty = fields.Float(string='Số lượng yêu cầu', required=True, default=1.0)
    qty_approve = fields.Float(string='Số lượng phê duyệt', default=0.0)
    total = fields.Float(string='Tổng giá trị', compute='_compute_total', store=True)
    sequence = fields.Integer(string='STT', default=0, readonly=True)

    # Tông giá sản phẩm
    @api.depends('qty', 'product_id')
    def _compute_total(self):
        for line in self:
            line.total = line.qty * (line.product_id.list_price or 0.0)

    # Cộng dồn sản phẩm khi trùng sản phẩm
    @api.model
    def create(self, vals):
        request = self.env['purchase.request'].browse(vals.get('request_id'))
        if request.state != 'draft':
            raise UserError("Không thể thêm chi tiết yêu cầu khi trạng thái không phải là Dự thảo.")
        # Kiểm tra nếu sản phẩm đã tồn tại trong danh sách dòng sản phẩm
        existing_line = self.env['purchase.request.line'].search([
            ('request_id', '=', vals.get('request_id')),
            ('product_id', '=', vals.get('product_id')),
        ], limit=1)

        if existing_line:
            # Cộng dồn số lượng nếu sản phẩm đã tồn tại
            existing_line.qty += vals.get('qty', 1.0)
            return existing_line
        else:
            # Nếu không tồn tại, tạo dòng mới
            return super(PurchaseLine, self).create(vals)

    def write(self, vals):
        # Ngăn sửa đổi sản phẩm nếu đã được phê duyệt
        if 'product_id' in vals or 'qty' in vals:
            for line in self:
                if line.request_id.state != 'draft':
                    raise UserError("Không thể chỉnh sửa chi tiết yêu cầu khi trạng thái không phải là Dự thảo.")
        return super(PurchaseLine, self).write(vals)

    def unlink(self):
        for line in self:
            if line.request_id.state != 'draft':
                raise UserError("Không thể xóa chi tiết yêu cầu khi trạng thái không phải là Dự thảo.")
        return super(PurchaseLine, self).unlink()


class RejectReasonWizard(models.TransientModel):
    _name = 'reject.reason.wizard'
    _description = 'Reject Reason Wizard'

    reject_reason = fields.Text(string="Lý do từ chối")
    reject_type = fields.Selection([
        ('not_suitable', 'Không phù hợp'),
        ('too_expensive', 'Quá đắt'),
        ('other', 'Lý do khác')
    ], string="Lý do từ chối", required=True, default='not_suitable')

    def action_confirm_reject(self):
        # Lấy active_id (ID của bản ghi purchase.request đang mở)
        active_id = self.env.context.get('active_id')
        purchase_request = self.env['purchase.request'].browse(active_id)

        if purchase_request:
            # Tạo lý do từ chối
            reason = self.reject_reason if self.reject_type == 'other' else dict(
                self._fields['reject_type'].selection).get(self.reject_type)
            # Cập nhật lý do từ chối và trạng thái
            purchase_request.write({
                'reject_reason': reason,
                'state': 'cancel',
            })







