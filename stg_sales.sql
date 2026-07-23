with source as (

    select * from {{ source('vehicle_sales', 'sales') }}

),

renamed as (

	select
		sale_id,
		vehicle_id,
		price::numeric(12,2) as price,
		total_sale::numeric(12,2) as total_sale,
		date_sold::date as date_sold
	
	from source
	
)

select * from renamed
