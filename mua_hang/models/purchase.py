from odoo import models, fields, api
from odoo.exceptions import UserError


class Purchase(models.Model):
    _name = "purchase.request"
    _description = "Purchase Request"

    name = fields.Char(string="Yêu cầu tham chiếu", required=True, readonly=True, default="New")
    department_id = fields.Many2one('hr.department', string='Phòng ban', required=True,)
    request_id = fields.Many2one('res.users', string='Người yêu cầu', required=True)
    approver_id = fields.Many2one('res.users', string='Người phê duyệt', readonly=True)
    date = fields.Date(string='Ngày yêu cầu', default=fields.Date.context_today)
    date_approve = fields.Date(string='Ngày phê duyệt', readonly=True)
    request_line_ids = fields.One2many('purchase.request.line', 'request_id', string='Chi tiết yêu cầu mua hàng')
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

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('purchase.request.sequence') or 'New'
        return super(Purchase, self).create(vals)

    @api.depends('request_line_ids.qty')
    def _compute_total_qty(self):
        for record in self:
            record.total_qty = sum(line.qty for line in record.request_line_ids)

    @api.depends('request_line_ids.total')
    def _compute_total_amount(self):
        for record in self:
            record.total_amount = sum(line.total for line in record.request_line_ids)

    def action_submit(self):
        for record in self:
            if record.state != 'draft':
                raise UserError("Chỉ có thể gửi yêu cầu ở trạng thái dự thảo.")
            record.state = 'wait'

    def action_reset_to_draft(self):
        for record in self:
            if record.state != 'wait':
                raise UserError("Chỉ có thể quay lại từ trạng thái chờ phê duyệt.")
            record.state = 'draft'

    def action_approve(self):
        for record in self:
            if record.state != 'wait':
                raise UserError("Chỉ có thể phê duyệt yêu cầu ở trạng thái chờ phê duyệt.")
            record.state = 'approved'
            record.date_approve = fields.Date.context_today(self)
            record.approver_id = self.env.user.id
            record.state = 'approved'

    def action_cancel(self):
        for record in self:
            if record.state != 'wait':
                raise UserError("Chỉ có thể từ chối yêu cầu ở trạng thái chờ phê duyệt.")
            if not record.reject_reason:
                raise UserError("Vui lòng nhập lý do từ chối.")
            record.state = 'cancel'

    def unlink(self):
        for record in self:
            if record.state != 'draft':
                raise UserError("Bạn không được phép xóa ở trạng thái khác dự thảo.")
            record.request_line_ids.unlink()
        return super(Purchase, self).unlink()

    def action_browse(self):
        for record in self:
            if record.state != 'wait':
                raise UserError(f"Phiếu yêu cầu '{record.name}' không ở trạng thái Chờ phê duyệt.")
            record.state = 'approved'
            record.date_approve = fields.Date.context_today(self)
            record.approver_id = self.env.user.id

class PurchaseLine(models.Model):
    _name = "purchase.request.line"
    _description = "Purchase Request Line"

    request_id = fields.Many2one('purchase.request', sring='Yêu cầu mua hàng', required=True)
    product_id = fields.Many2one('product.template', string='Sản phẩm', required=True)
    uom_id = fields.Many2one('uom.uom', string='Đơn vị tính', required=True)
    qty = fields.Float(string='Số lượng yêu cầu', required=True, default=1.0)
    qty_approve = fields.Float(string='Số lượng phê duyệt', default=0.0)
    total = fields.Float(string='Tổng giá trị', compute='_compute_total', store=True)

    @api.depends('qty', 'product_id')
    def _compute_total(self):
        for line in self:
            line.total = line.qty * (line.product_id.list_price or 0.0)

    @api.model
    def create(self, vals):
        request = self.env['purchase.request'].browse(vals.get('request_id'))
        if request.state != 'draft':
            raise UserError("Không thể thêm chi tiết yêu cầu khi trạng thái không phải là Dự thảo.")
        return super(PurchaseLine, self).create(vals)

    def write(self, vals):
        for line in self:
            if line.request_id.state != 'draft':
                raise UserError("Không thể chỉnh sửa chi tiết yêu cầu khi trạng thái không phải là Dự thảo.")
        return super(PurchaseLine, self).write(vals)

    def unlink(self):
        for line in self:
            if line.request_id.state != 'draft':
                raise UserError("Không thể xóa chi tiết yêu cầu khi trạng thái không phải là Dự thảo.")
        return super(PurchaseLine, self).unlink()



