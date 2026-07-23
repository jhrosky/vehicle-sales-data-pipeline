with source as (

    select * from {{ source('vehicle_sales', 'vehicles') }}

),

renamed as (

	select
		vehicle_id,
		make,
		model,
		year,
		vin,
		mileage,
		dealership_id,
		date_listed::date as date_listed
	
	from source
	
)

select * from renamed
